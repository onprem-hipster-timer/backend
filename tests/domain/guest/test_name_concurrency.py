"""PostgreSQL에서 같은 리소스에 게스트 생성·이름 변경이 몰릴 때

이름이 겹치지 않는 것은 UNIQUE (resource_type, resource_id, name)이 보장한다. SQLite는 동시 쓰기를 다르게 다루므로
TEST_DATABASE_URL이 PostgreSQL일 때만 돈다. 가짜 Kratos admin 응답을 늦춰 요청들이 이름 확인과 저장 사이에서 겹치게 한다.
"""
import asyncio
import os
import time
import uuid

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import create_engine, text

from app.domain.guest import service
from app.domain.guest.exceptions import GuestNameTakenError
from app.domain.guest.host import GuestHostStatus
from app.domain.guest.schema.dto import GuestCreate
from app.models.visibility import ResourceType
from tests.domain.guest.helpers import guest_rows, make_guest

_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
_IS_POSTGRESQL = _DATABASE_URL.startswith("postgresql")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _IS_POSTGRESQL, reason="requires PostgreSQL via TEST_DATABASE_URL for concurrent writes"),
]

KRATOS_DELAY_SECONDS = 0.2
POOL_SIZE = 2
# 몰린 요청이 모두 끝나야 하는 시간과, 그동안 다른 요청이 응답해야 하는 시간
BOUND_SECONDS = 60
QUICK_SECONDS = 2


@pytest.fixture
def slow_kratos(kratos):
    admin, public = kratos.admin, kratos.public

    async def slow_admin(request):
        await asyncio.sleep(KRATOS_DELAY_SECONDS)
        return admin(request)

    async def slow_public(request):
        if request.url.path == "/self-service/settings":
            await asyncio.sleep(KRATOS_DELAY_SECONDS)
        return await public(request)

    kratos.admin, kratos.public = slow_admin, slow_public
    return kratos


@pytest.fixture
def resource(host):
    resource_id = uuid.uuid4()
    host.statuses[resource_id] = GuestHostStatus.OPEN
    return resource_id


def _create(resource, name="민수", password="1234") -> GuestCreate:
    return GuestCreate(resource_type=ResourceType.MEETING, resource_id=resource, name=name, password=password)


def _idle_in_transaction() -> int:
    probe = create_engine(_DATABASE_URL)
    try:
        with probe.connect() as conn:
            return conn.execute(text(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname = current_database() AND state = 'idle in transaction' AND pid <> pg_backend_pid()"
            )).scalar()
    finally:
        probe.dispose()


# ============ 같은 이름 ============

@pytest.mark.asyncio
@pytest.mark.usefixtures("guest_db")
async def test_concurrent_creates_of_one_name_leave_one_row_and_one_identity(slow_kratos, resource):
    make_guest(slow_kratos, resource, name="영희")

    results = await asyncio.gather(
        *(service.create(_create(resource, password=f"p{i}")) for i in range(5)),
        return_exceptions=True,
    )

    created = [r for r in results if not isinstance(r, BaseException)]
    refused = [r for r in results if isinstance(r, GuestNameTakenError)]
    assert (len(created), len(refused)) == (1, 4), results
    assert sorted(row.name for row in guest_rows()) == ["민수", "영희"]
    assert len(slow_kratos.identities) == 2
    assert _idle_in_transaction() == 0


@pytest.mark.asyncio
@pytest.mark.usefixtures("guest_db")
async def test_concurrent_rename_and_create_of_one_name_leave_one_holder(slow_kratos, resource):
    guest = make_guest(slow_kratos, resource, name="민수")
    traits = {**slow_kratos.identities[guest.identity_id]["traits"], "name": "철수"}

    rename, create = await asyncio.gather(
        service.settings_change_allowed("profile", guest.identity_id, "guest", traits),
        service.create(_create(resource, name="철수")),
        return_exceptions=True,
    )

    assert [row.name for row in guest_rows()].count("철수") == 1
    assert (rename is True) != (not isinstance(create, BaseException)), (rename, create)
    assert len(slow_kratos.identities) == len(guest_rows())


# ============ 풀이 작을 때 ============

@pytest.fixture
def small_pool(guest_client):
    """guest_client의 설정을 쓰고, 앱 세션 매니저만 연결 POOL_SIZE개인 엔진으로 바꾼다"""
    from app.db.session import _session_manager

    engine = create_engine(_DATABASE_URL, pool_size=POOL_SIZE, max_overflow=0)
    original = _session_manager.engine
    _session_manager.engine = engine
    try:
        yield engine
    finally:
        _session_manager.engine = original
        engine.dispose()


@pytest_asyncio.fixture
async def api():
    from app.main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=60) as client:
        yield client


async def _rename(api, kratos, guest, name):
    token = f"token-{guest.identity_id}"
    kratos.sessions[token] = guest.identity_id
    handle = kratos.identities[guest.identity_id]["traits"]["handle"]
    return await api.post(
        f"/auth/self-service/settings?flow={uuid.uuid4()}",
        json={"method": "profile", "traits": {"handle": handle, "name": name}},
        headers={"X-Session-Token": token},
    )


async def _elapsed(request) -> float:
    """다른 요청들이 시작된 뒤 request가 끝나기까지 걸린 시간"""
    await asyncio.sleep(KRATOS_DELAY_SECONDS)
    started = time.monotonic()
    await request()
    return time.monotonic() - started


@pytest.mark.asyncio
async def test_creates_and_renames_on_one_resource_with_small_pool(small_pool, slow_kratos, host, resource, api):
    other = uuid.uuid4()
    host.statuses[other] = GuestHostStatus.OPEN
    guest = make_guest(slow_kratos, resource, name="민수")
    body = {"resource_type": "meeting", "resource_id": str(resource), "password": "1234"}

    creates = [api.post("/v1/guests", json={**body, "name": f"g{i}"}) for i in range(30)]
    renames = [_rename(api, slow_kratos, guest, f"r{i}") for i in range(10)]

    async def run():
        return await asyncio.gather(
            asyncio.gather(*creates, *renames),
            _elapsed(lambda: api.get("/health")),
            _elapsed(lambda: api.post(
                "/v1/guests/lookup", json={"resource_type": "meeting", "resource_id": str(other), "name": "x"}
            )),
        )

    responses, health_seconds, lookup_seconds = await asyncio.wait_for(run(), BOUND_SECONDS)

    create_statuses = [r.status_code for r in responses[:30]]
    rename_statuses = [r.status_code for r in responses[30:]]
    assert set(create_statuses) <= {201, 409, 503}, create_statuses
    assert set(rename_statuses) <= {200, 400, 409, 503}, rename_statuses
    assert 201 in create_statuses and 200 in rename_statuses
    assert health_seconds < QUICK_SECONDS
    assert lookup_seconds < QUICK_SECONDS
    rows = guest_rows()
    assert len(rows) == 1 + create_statuses.count(201)
    assert len({row.name for row in rows}) == len(rows)
    assert _idle_in_transaction() == 0
