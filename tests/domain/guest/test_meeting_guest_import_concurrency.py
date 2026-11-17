"""PostgreSQL에서 게스트 가져오기가 다른 요청과 겹칠 때 (POST /v1/meetings/{meeting_id}/guest-import)

가져오기 트랜잭션은 게스트 행을 FOR UPDATE로 잠그고 다시 확인한 뒤, 회원·게스트 참여자와 그 가능 시간을 NOWAIT로
잠근다. 그래서 겹친 요청은 한쪽 결과만 남는다.

- 같은 게스트를 두 번 가져오면 하나만 가져오고 다른 하나는 게스트 행을 기다렸다가 404다
- 게스트의 가능 시간 저장이 진행 중이면 가져오기는 기다리지 않고 409이고, 가져오기가 먼저 잠갔으면 저장이 실패한다
- 게스트 자기 삭제·생성자의 참여자 빼기와 겹치면, 먼저 게스트 행을 잡은 쪽만 일어난다
- 커밋 전에는 다른 연결에서 바뀐 것이 보이지 않는다

SQLite는 행을 잠그지 않으므로 TEST_DATABASE_URL이 PostgreSQL일 때만 돈다. 한쪽 트랜잭션을 커밋 전에 멈춰 두고
다른 쪽을 시작한다.
"""
import asyncio
import os
import threading
import time
import uuid

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import create_engine, text
from sqlmodel import Session, select

from app.db.session import _session_manager
from app.domain.consent import service as consent_service
from app.domain.guest import service as guest_service
from app.domain.meeting import service as meeting_service
from app.domain.meeting.schema.dto import TimeSlotCreate
from app.domain.meeting.visitor_service import MeetingGuestService
from app.models.guest import Guest
from app.models.meeting import MeetingParticipant, MeetingTimeSlot
from tests.domain.guest.helpers import guest_rows, make_guest
from tests.domain.guest.meeting_helpers import MEMBER, OWNER, create_meeting, participate, set_slots

_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
_IS_POSTGRESQL = _DATABASE_URL.startswith("postgresql")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _IS_POSTGRESQL, reason="requires PostgreSQL via TEST_DATABASE_URL for row locks"),
]

# 멈춘 트랜잭션 뒤에서 다른 쪽이 끝나지 않는지 지켜보는 시간과, 어떤 기다림이든 넘지 않는 시간
HOLD_SECONDS = 1
BOUND_SECONDS = 30
OTHER_MEMBER = "member-2"

GUEST_SLOTS = [
    {"start_time": "2099-03-02T09:00:00Z", "end_time": "2099-03-02T10:00:00Z"},
    {"start_time": "2099-03-03T09:00:00Z", "end_time": "2099-03-03T11:00:00Z", "kind": "unavailable"},
]
GUEST_ANSWER = [
    ("2099-03-02T09:00:00+0000", "2099-03-02T10:00:00+0000", "available"),
    ("2099-03-03T09:00:00+0000", "2099-03-03T11:00:00+0000", "unavailable"),
]


class Hold:
    """감싼 함수의 첫 호출을 멈춘다. after면 원래 함수를 부른 뒤, 아니면 부르기 전에 멈춘다"""

    def __init__(self):
        self.reached = threading.Event()
        self.released = threading.Event()
        self._used = False

    def wrap(self, original, after: bool = False):
        def run(*args, **kwargs):
            first, self._used = not self._used, True
            if first and not after:
                self._stop()
            result = original(*args, **kwargs)
            if first and after:
                self._stop()
            return result
        return run

    def _stop(self):
        self.reached.set()
        self.released.wait(BOUND_SECONDS)


@pytest.fixture
def hold():
    held = Hold()
    yield held
    held.released.set()


@pytest.fixture
def client(guest_client, meeting_host):
    return guest_client


@pytest.fixture
def meeting_id(client, tokens) -> str:
    return create_meeting(client, tokens)


@pytest.fixture
def guest(client, tokens, kratos, meeting_id):
    """가능 시간 GUEST_SLOTS를 넣은 게스트"""
    guest = make_guest(kratos, uuid.UUID(meeting_id), "민수")
    headers = tokens.guest(guest.identity_id)
    participant_id = participate(client, meeting_id, headers)["id"]
    assert set_slots(client, meeting_id, participant_id, headers, GUEST_SLOTS).status_code == 200
    return guest


@pytest.fixture
def guest_participant_id(guest) -> uuid.UUID:
    with _session_manager.get_session() as session:
        return session.exec(select(MeetingParticipant.id).where(MeetingParticipant.guest_id == guest.id)).one()


@pytest_asyncio.fixture
async def api(client):
    from app.main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=60) as api:
        yield api


def _import(api, tokens, meeting_id, guest, member: str = MEMBER):
    return api.post(
        f"/v1/meetings/{meeting_id}/guest-import",
        json={"guest_token": tokens.make(guest.identity_id, "guest", name="게스트")},
        headers=tokens.member(member),
    )


async def _wait_until(event: threading.Event) -> None:
    assert await asyncio.to_thread(event.wait, BOUND_SECONDS)


def _probe(sql: str) -> int:
    probe = create_engine(_DATABASE_URL)
    try:
        with probe.connect() as conn:
            return conn.execute(text(sql)).scalar()
    finally:
        probe.dispose()


def _lock_waiters() -> int:
    """이 DB에서 행 잠금을 기다리는 연결 수"""
    return _probe(
        "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND wait_event_type = 'Lock'"
    )


def _idle_in_transaction() -> int:
    return _probe(
        "SELECT count(*) FROM pg_stat_activity "
        "WHERE datname = current_database() AND state = 'idle in transaction' AND pid <> pg_backend_pid()"
    )


def _answers() -> dict:
    """참여자(회원은 sub, 게스트는 'guest')마다 가능 시간"""
    with _session_manager.get_session() as session:
        answers = {}
        for participant in session.exec(select(MeetingParticipant)).all():
            key = participant.user_id or "guest"
            slots = session.exec(
                select(MeetingTimeSlot).where(MeetingTimeSlot.participant_id == participant.id)
            ).all()
            answers[key] = sorted(
                (s.start_time.strftime("%Y-%m-%dT%H:%M:%S+0000"), s.end_time.strftime("%Y-%m-%dT%H:%M:%S+0000"),
                 s.kind.value)
                for s in slots
            )
        return answers


def _orphan_slots() -> int:
    return _probe(
        "SELECT count(*) FROM meeting_time_slot s "
        "LEFT JOIN meeting_participant p ON p.id = s.participant_id WHERE p.id IS NULL"
    )


# ============ 같은 게스트를 두 번 ============

@pytest.mark.asyncio
async def test_concurrent_imports_of_one_guest_import_once(api, tokens, kratos, meeting_id, guest, hold, monkeypatch):
    monkeypatch.setattr(consent_service, "delete_consents", hold.wrap(consent_service.delete_consents, after=True))
    first = asyncio.create_task(_import(api, tokens, meeting_id, guest))
    await _wait_until(hold.reached)

    # 첫 가져오기는 쓸 것을 다 쓰고 커밋 전에 멈췄다. 다른 연결에는 아무것도 바뀌지 않았다
    assert _answers() == {"guest": GUEST_ANSWER}
    assert [g.id for g in guest_rows()] == [guest.id]

    second = asyncio.create_task(_import(api, tokens, meeting_id, guest, member=OTHER_MEMBER))
    done, _ = await asyncio.wait({second}, timeout=HOLD_SECONDS)
    assert not done
    assert _lock_waiters() == 1

    hold.released.set()
    first, second = await asyncio.wait_for(asyncio.gather(first, second), BOUND_SECONDS)

    assert first.status_code == 200, first.text
    assert (second.status_code, second.json()["error_type"]) == (404, "GuestNotFoundError")
    assert _answers() == {MEMBER: GUEST_ANSWER}
    assert guest_rows() == []
    assert kratos.deleted == [guest.identity_id]
    assert _idle_in_transaction() == 0


@pytest.mark.asyncio
async def test_imports_of_two_guests_into_one_member_do_not_mix(
        client, api, tokens, kratos, meeting_id, guest, hold, monkeypatch,
):
    other = make_guest(kratos, uuid.UUID(meeting_id), "지수")
    headers = tokens.guest(other.identity_id)
    other_participant = participate(client, meeting_id, headers)["id"]
    other_slot = {"start_time": "2099-03-04T09:00:00Z", "end_time": "2099-03-04T10:00:00Z"}
    assert set_slots(client, meeting_id, other_participant, headers, [other_slot]).status_code == 200
    participate(client, meeting_id, tokens.member(MEMBER))
    monkeypatch.setattr(meeting_service, "merge_time_slots", hold.wrap(meeting_service.merge_time_slots))
    first = asyncio.create_task(_import(api, tokens, meeting_id, guest))
    await _wait_until(hold.reached)

    started = time.monotonic()
    second = await _import(api, tokens, meeting_id, other)

    assert (second.status_code, second.json()["error_type"]) == (409, "GuestImportConflictError")
    assert time.monotonic() - started < HOLD_SECONDS
    hold.released.set()
    assert (await asyncio.wait_for(first, BOUND_SECONDS)).status_code == 200
    retried = await _import(api, tokens, meeting_id, other)
    assert retried.status_code == 200, retried.text
    assert _answers() == {MEMBER: sorted(GUEST_ANSWER + [
        ("2099-03-04T09:00:00+0000", "2099-03-04T10:00:00+0000", "available"),
    ])}
    assert guest_rows() == []
    assert _idle_in_transaction() == 0


# ============ 게스트의 가능 시간 저장 ============

NEW_GUEST_SLOT = TimeSlotCreate(start_time="2099-03-05T09:00:00Z", end_time="2099-03-05T10:00:00Z")
NEW_GUEST_ANSWER = [("2099-03-05T09:00:00+0000", "2099-03-05T10:00:00+0000", "available")]


def _save_as_guest(guest: Guest, meeting_id: str, participant_id: uuid.UUID, before_commit: threading.Event | None,
                   released: threading.Event | None):
    """게스트의 PUT /availability와 같은 DB 작업을 자기 세션으로 하고 커밋한다. before_commit이 있으면 커밋 전에 멈춘다"""
    with Session(_session_manager.engine) as session:
        guest_row = session.get(Guest, guest.id)
        MeetingGuestService(session, guest_row).set_time_slots(uuid.UUID(meeting_id), participant_id, [NEW_GUEST_SLOT])
        session.flush()
        if before_commit is not None:
            before_commit.set()
            released.wait(BOUND_SECONDS)
        session.commit()


@pytest.mark.asyncio
async def test_import_while_guest_save_is_in_flight_is_409_then_imports_the_saved_answer(
        api, tokens, kratos, meeting_id, guest, guest_participant_id, hold,
):
    save = asyncio.create_task(asyncio.to_thread(
        _save_as_guest, guest, meeting_id, guest_participant_id, hold.reached, hold.released,
    ))
    await _wait_until(hold.reached)

    started = time.monotonic()
    refused = await _import(api, tokens, meeting_id, guest)

    assert (refused.status_code, refused.json()["error_type"]) == (409, "GuestImportConflictError")
    assert time.monotonic() - started < HOLD_SECONDS
    assert MEMBER not in _answers()
    assert [g.id for g in guest_rows()] == [guest.id]
    assert kratos.deleted == []
    hold.released.set()
    await asyncio.wait_for(save, BOUND_SECONDS)

    imported = await _import(api, tokens, meeting_id, guest)

    assert imported.status_code == 200, imported.text
    assert _answers() == {MEMBER: NEW_GUEST_ANSWER}
    assert guest_rows() == []
    assert _idle_in_transaction() == 0


@pytest.mark.asyncio
async def test_guest_save_waiting_behind_import_fails_and_import_keeps_the_earlier_answer(
        api, tokens, kratos, meeting_id, guest, guest_participant_id, hold, monkeypatch,
):
    monkeypatch.setattr(meeting_service, "merge_time_slots", hold.wrap(meeting_service.merge_time_slots))
    imported = asyncio.create_task(_import(api, tokens, meeting_id, guest))
    await _wait_until(hold.reached)

    save = asyncio.create_task(asyncio.to_thread(_save_as_guest, guest, meeting_id, guest_participant_id, None, None))
    done, _ = await asyncio.wait({save}, timeout=HOLD_SECONDS)
    assert not done
    assert _lock_waiters() == 1

    hold.released.set()
    assert (await asyncio.wait_for(imported, BOUND_SECONDS)).status_code == 200
    with pytest.raises(Exception) as failed:
        await asyncio.wait_for(save, BOUND_SECONDS)

    assert "foreign key" in str(failed.value).lower()
    assert _answers() == {MEMBER: GUEST_ANSWER}
    assert _orphan_slots() == 0
    assert guest_rows() == []
    assert _idle_in_transaction() == 0


# ============ 게스트 자기 삭제, 생성자의 참여자 빼기 ============

def _discard(api, tokens, kind: str, meeting_id: str, guest, guest_participant_id):
    if kind == "self":
        return guest_service.discard_guest(guest.identity_id)
    return api.delete(f"/v1/meetings/{meeting_id}/participants/{guest_participant_id}", headers=tokens.member(OWNER))


@pytest.mark.parametrize("kind", ["self", "owner"])
@pytest.mark.asyncio
async def test_discard_waits_for_open_import_which_keeps_the_answer(
        api, tokens, kratos, meeting_id, guest, guest_participant_id, hold, monkeypatch, kind,
):
    monkeypatch.setattr(meeting_service, "merge_time_slots", hold.wrap(meeting_service.merge_time_slots))
    imported = asyncio.create_task(_import(api, tokens, meeting_id, guest))
    await _wait_until(hold.reached)

    discard = asyncio.create_task(_discard(api, tokens, kind, meeting_id, guest, guest_participant_id))
    done, _ = await asyncio.wait({discard}, timeout=HOLD_SECONDS)
    assert not done
    assert _lock_waiters() == 1

    hold.released.set()
    imported, discarded = await asyncio.wait_for(asyncio.gather(imported, discard), BOUND_SECONDS)

    assert imported.status_code == 200, imported.text
    if kind == "owner":
        assert discarded.status_code == 200
    assert _answers() == {MEMBER: GUEST_ANSWER}
    assert guest_rows() == []
    assert kratos.deleted == [guest.identity_id]
    assert _idle_in_transaction() == 0


@pytest.mark.parametrize("kind", ["self", "owner"])
@pytest.mark.asyncio
async def test_import_waits_for_open_discard_and_is_not_found(
        api, tokens, kratos, meeting_id, guest, guest_participant_id, hold, monkeypatch, kind,
):
    monkeypatch.setattr(consent_service, "delete_consents", hold.wrap(consent_service.delete_consents, after=True))
    discard = asyncio.create_task(_discard(api, tokens, kind, meeting_id, guest, guest_participant_id))
    await _wait_until(hold.reached)

    imported = asyncio.create_task(_import(api, tokens, meeting_id, guest))
    done, _ = await asyncio.wait({imported}, timeout=HOLD_SECONDS)
    assert not done
    assert _lock_waiters() == 1

    hold.released.set()
    _, imported = await asyncio.wait_for(asyncio.gather(discard, imported), BOUND_SECONDS)

    assert (imported.status_code, imported.json()["error_type"]) == (404, "GuestNotFoundError")
    assert _answers() == {}
    assert guest_rows() == []
    assert kratos.deleted == [guest.identity_id]
    assert _idle_in_transaction() == 0
