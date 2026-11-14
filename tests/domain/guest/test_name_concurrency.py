"""PostgreSQL에서 같은 리소스의 게스트 생성·이름 변경이 하나씩 처리되는지

SQLite에서는 리소스 잠금을 걸지 않으므로 TEST_DATABASE_URL이 PostgreSQL일 때만 돈다.
가짜 Kratos admin 응답을 늦춰 두 요청이 이름 확인과 생성 사이에서 겹치게 한다.
"""
import asyncio
import os
import uuid

import pytest

from app.domain.guest import service
from app.domain.guest.exceptions import GuestNameTakenError
from app.domain.guest.host import GuestHostStatus
from app.domain.guest.schema.dto import GuestCreate
from app.models.visibility import ResourceType
from tests.domain.guest.helpers import guest_rows, make_guest

_IS_POSTGRESQL = os.environ.get("TEST_DATABASE_URL", "").startswith("postgresql")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _IS_POSTGRESQL, reason="requires PostgreSQL via TEST_DATABASE_URL for advisory locks"),
    pytest.mark.usefixtures("guest_db"),
]

KRATOS_DELAY_SECONDS = 0.2


@pytest.fixture
def slow_kratos(kratos):
    admin = kratos.admin

    async def delayed(request):
        await asyncio.sleep(KRATOS_DELAY_SECONDS)
        return admin(request)

    kratos.admin = delayed
    return kratos


@pytest.fixture
def resource(host):
    resource_id = uuid.uuid4()
    host.statuses[resource_id] = GuestHostStatus.OPEN
    return resource_id


def _create(resource, name="민수", password="1234") -> GuestCreate:
    return GuestCreate(resource_type=ResourceType.MEETING, resource_id=resource, name=name, password=password)


async def _names(kratos) -> list[str]:
    return sorted(kratos.name_of(row.identity_id) for row in guest_rows())


@pytest.mark.asyncio
async def test_concurrent_creates_of_one_name_make_exactly_one_guest(slow_kratos, resource):
    # 이미 게스트가 있어야 이름 확인이 Kratos를 부른다 (빈 리소스는 바로 생성으로 간다)
    make_guest(slow_kratos, resource, name="영희")

    results = await asyncio.gather(
        *(service.create(_create(resource, password=f"p{i}")) for i in range(4)),
        return_exceptions=True,
    )

    created = [r for r in results if not isinstance(r, BaseException)]
    refused = [r for r in results if isinstance(r, GuestNameTakenError)]
    assert len(created) == 1
    assert len(refused) == 3
    assert await _names(slow_kratos) == ["민수", "영희"]
    assert len(slow_kratos.identities) == 2


@pytest.mark.asyncio
async def test_concurrent_creates_in_empty_resource_make_exactly_one_guest(slow_kratos, resource):
    results = await asyncio.gather(
        *(service.create(_create(resource, password=f"p{i}")) for i in range(3)),
        return_exceptions=True,
    )
    assert sum(not isinstance(r, BaseException) for r in results) == 1
    assert len(guest_rows()) == 1


@pytest.mark.asyncio
async def test_concurrent_creates_in_two_resources_do_not_wait_for_each_other(slow_kratos, host, resource):
    other = uuid.uuid4()
    host.statuses[other] = GuestHostStatus.OPEN
    results = await asyncio.gather(service.create(_create(resource)), service.create(_create(other)))
    assert len(results) == 2
    assert len(guest_rows()) == 2


@pytest.mark.asyncio
async def test_rename_and_create_of_one_name_leave_one_holder(slow_kratos, resource):
    guest = make_guest(slow_kratos, resource, name="민수")

    async def rename():
        async with service.rename_submission(guest.identity_id, "철수") as allowed:
            # Kratos가 설정 훅을 부른 뒤 이름을 저장하는 자리
            traits = {**slow_kratos.identities[guest.identity_id]["traits"], "name": "철수"}
            if allowed and await service.settings_change_allowed("profile", guest.identity_id, "guest", traits):
                await asyncio.sleep(KRATOS_DELAY_SECONDS)
                slow_kratos.identities[guest.identity_id]["traits"] = traits
                return True
            return False

    results = await asyncio.gather(rename(), service.create(_create(resource, name="철수")), return_exceptions=True)

    assert (await _names(slow_kratos)).count("철수") == 1
    renamed, created = results
    assert (renamed is True) != (not isinstance(created, BaseException))
