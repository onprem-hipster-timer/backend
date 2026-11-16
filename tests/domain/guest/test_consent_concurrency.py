"""PostgreSQL에서 게스트의 약관 동의 기록과 폐기가 겹칠 때

동의 기록(record_consent)은 커밋할 때까지 게스트 행을 잠근다. 폐기(discard_guest, discard_resource_guests)의 게스트 행
삭제는 그 잠금이 풀린 뒤 동의를 함께 지우고, 폐기가 먼저 행을 지웠으면 동의 기록은 행을 찾지 못해
GuestAccessDeniedError다. SQLite는 행을 잠그지 않으므로 TEST_DATABASE_URL이 PostgreSQL일 때만 돈다.
한쪽 트랜잭션을 커밋 전에 멈춰 두고 다른 쪽을 시작한다.
"""
import asyncio
import os
import threading
import uuid

import pytest
from sqlalchemy import create_engine, text

from app.domain.consent import service as consent_service
from app.domain.consent.schema.dto import ConsentCreate
from app.domain.guest import service
from app.domain.guest.exceptions import GuestAccessDeniedError
from app.domain.guest.model import Guest
from app.models.visibility import ResourceType
from tests.domain.guest.helpers import consent_body, consent_rows, guest_rows, make_guest

_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
_IS_POSTGRESQL = _DATABASE_URL.startswith("postgresql")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _IS_POSTGRESQL, reason="requires PostgreSQL via TEST_DATABASE_URL for row locks"),
]

# 멈춘 트랜잭션 뒤에서 다른 쪽이 끝나지 않는지 지켜보는 시간과, 어떤 기다림이든 넘지 않는 시간
HOLD_SECONDS = 1
BOUND_SECONDS = 30


@pytest.fixture
def released():
    """멈춘 트랜잭션을 놓는 신호. 테스트가 중간에 실패해도 끝에서 놓는다"""
    event = threading.Event()
    yield event
    event.set()


def _discard(kind: str, guest: Guest):
    if kind == "guest":
        return service.discard_guest(guest.identity_id)
    return service.discard_resource_guests(ResourceType.MEETING, guest.resource_id)


def _record_consent(guest: Guest):
    return service.record_consent(guest.identity_id, ConsentCreate(**consent_body()))


async def _wait_until(event: threading.Event) -> None:
    assert await asyncio.to_thread(event.wait, BOUND_SECONDS)


def _lock_waiters() -> int:
    """이 DB에서 행 잠금을 기다리는 연결 수"""
    probe = create_engine(_DATABASE_URL)
    try:
        with probe.connect() as conn:
            return conn.execute(text(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname = current_database() AND wait_event_type = 'Lock'"
            )).scalar()
    finally:
        probe.dispose()


@pytest.mark.parametrize("kind", ["guest", "resource"])
@pytest.mark.asyncio
@pytest.mark.usefixtures("guest_db")
async def test_discard_waits_for_open_consent_and_removes_it(kratos, monkeypatch, released, kind):
    guest = make_guest(kratos, uuid.uuid4())
    guest_read = threading.Event()
    record = consent_service.record_consent

    def record_after_release(session, sub, data):
        guest_read.set()
        released.wait(BOUND_SECONDS)
        return record(session, sub, data)

    monkeypatch.setattr(consent_service, "record_consent", record_after_release)
    consent = asyncio.create_task(_record_consent(guest))
    await _wait_until(guest_read)

    discard = asyncio.create_task(_discard(kind, guest))
    done, _ = await asyncio.wait({discard}, timeout=HOLD_SECONDS)
    assert not done
    assert _lock_waiters() == 1

    released.set()
    await asyncio.wait_for(asyncio.gather(consent, discard), BOUND_SECONDS)

    assert guest_rows() == []
    assert consent_rows() == set()
    assert kratos.deleted == [guest.identity_id]


@pytest.mark.parametrize("kind", ["guest", "resource"])
@pytest.mark.asyncio
@pytest.mark.usefixtures("guest_db")
async def test_consent_waits_for_open_discard_and_is_refused(kratos, monkeypatch, released, kind):
    guest = make_guest(kratos, uuid.uuid4())
    rows_deleted = threading.Event()
    delete_consents = consent_service.delete_consents

    def delete_then_hold(session, subs):
        delete_consents(session, subs)
        rows_deleted.set()
        released.wait(BOUND_SECONDS)

    monkeypatch.setattr(consent_service, "delete_consents", delete_then_hold)
    discard = asyncio.create_task(_discard(kind, guest))
    await _wait_until(rows_deleted)

    consent = asyncio.create_task(_record_consent(guest))
    done, _ = await asyncio.wait({consent}, timeout=HOLD_SECONDS)
    assert not done
    assert _lock_waiters() == 1

    released.set()
    await asyncio.wait_for(discard, BOUND_SECONDS)
    with pytest.raises(GuestAccessDeniedError):
        await asyncio.wait_for(consent, BOUND_SECONDS)

    assert guest_rows() == []
    assert consent_rows() == set()
