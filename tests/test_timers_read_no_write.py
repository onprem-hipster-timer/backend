"""
타이머 조회가 DB를 쓰지 않는지 검증하는 E2E 테스트

조회 응답의 elapsed_time은 저장값이다. RUNNING 타이머의 현재 구간(now - started_at)은
클라이언트가 더한다. 조회 경로에서 서버가 이 구간을 세션의 객체에 더하면, GET이
트랜잭션을 커밋하면서 elapsed_time이 누적되고 updated_at이 바뀐다.
친구가 공유 타이머를 조회해도 소유자의 행이 바뀐다.

할당 시간을 넘긴 RUNNING 타이머는 조회 응답에서만 만료 표현(PAUSED)으로 보이고 행은 RUNNING 그대로다.
"""
from datetime import datetime, timedelta, UTC
from uuid import UUID

import pytest
from sqlalchemy import update
from sqlmodel import Session

from app.db.session import _session_manager
from app.domain.timer.model import TimerSession
from tests.conftest import TimerCommands

STORED_UPDATED_AT = datetime(2020, 1, 1)


def _create_timer(client) -> str:
    """RUNNING 타이머를 만들고 ID를 반환"""
    return TimerCommands(client).create_timer(title="조회 부작용 테스트")["id"]


def _backdate(timer_id: str) -> None:
    """started_at을 120초 전으로, updated_at을 고정값으로 DB에 직접 기록"""
    started_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=120)
    with Session(_session_manager.engine) as session:
        session.execute(
            update(TimerSession)
            .where(TimerSession.id == UUID(timer_id))
            .values(started_at=started_at, updated_at=STORED_UPDATED_AT)
        )
        session.commit()


def _stored(timer_id: str) -> tuple[int, datetime]:
    """새 세션으로 DB의 (elapsed_time, updated_at) 조회"""
    with Session(_session_manager.engine) as session:
        timer = session.get(TimerSession, UUID(timer_id))
        return timer.elapsed_time, timer.updated_at


def _find(body, timer_id: str) -> dict:
    timers = body if isinstance(body, list) else [body]
    return next(t for t in timers if t["id"] == timer_id)


def _make_friends(client_a, client_b) -> None:
    friend_code = client_b.get("/v1/users/me").json()["friend_code"]
    assert client_a.post("/v1/friends/requests", json={"friend_code": friend_code}).status_code == 201
    friendship_id = client_b.get("/v1/friends/requests/received").json()[0]["id"]
    assert client_b.post(f"/v1/friends/requests/{friendship_id}/accept").status_code == 200


def _assert_reads_do_not_write(client, path: str, timer_id: str) -> None:
    for _ in range(2):
        response = client.get(path)
        assert response.status_code == 200
        assert _stored(timer_id) == (0, STORED_UPDATED_AT)
        assert _find(response.json(), timer_id)["elapsed_time"] == 0


@pytest.mark.e2e
@pytest.mark.parametrize("path", [
    "/v1/timers",
    "/v1/timers/active",
    "/v1/timers/{timer_id}",
])
def test_owner_read_does_not_write_running_timer(multi_user_e2e, path):
    """소유자 조회는 RUNNING 타이머의 elapsed_time·updated_at을 바꾸지 않고 저장값을 반환"""
    owner = multi_user_e2e.as_user("owner")
    timer_id = _create_timer(owner)
    _backdate(timer_id)

    _assert_reads_do_not_write(owner, path.format(timer_id=timer_id), timer_id)


@pytest.mark.e2e
@pytest.mark.parametrize("path", [
    "/v1/timers?scope=shared",
    "/v1/timers/{timer_id}",
])
def test_friend_read_does_not_write_owner_timer(multi_user_e2e, path):
    """친구가 공유 타이머를 조회해도 소유자의 행은 바뀌지 않음"""
    owner = multi_user_e2e.as_user("owner")
    friend = multi_user_e2e.as_user("friend")
    timer_id = _create_timer(owner)
    assert owner.put(f"/v1/visibility/timer/{timer_id}", json={"level": "friends"}).status_code == 200
    _make_friends(owner, friend)
    _backdate(timer_id)

    _assert_reads_do_not_write(friend, path.format(timer_id=timer_id), timer_id)


@pytest.mark.e2e
@pytest.mark.parametrize("path", [
    "/v1/timers",
    "/v1/timers/active",
    "/v1/timers/{timer_id}",
])
def test_read_shows_expired_timer_without_writing(multi_user_e2e, path):
    """만료된 RUNNING 타이머는 PAUSED·elapsed=allocated·paused_at=만료 시각으로 보이고 행은 바뀌지 않음"""
    owner = multi_user_e2e.as_user("owner")
    timer = TimerCommands(owner).create_timer(title="만료 조회", allocated_duration=60)
    timer_id = timer["id"]
    started_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=90)
    with Session(_session_manager.engine) as session:
        session.execute(
            update(TimerSession)
            .where(TimerSession.id == UUID(timer_id))
            .values(started_at=started_at, updated_at=STORED_UPDATED_AT)
        )
        session.commit()
    expires_at = (started_at + timedelta(seconds=60)).replace(tzinfo=UTC, microsecond=0)

    for _ in range(2):
        response = owner.get(path.format(timer_id=timer_id))
        assert response.status_code == 200
        body = _find(response.json(), timer_id)
        assert body["status"] == "PAUSED"
        assert body["elapsed_time"] == 60
        paused_at = datetime.fromisoformat(body["paused_at"].replace("Z", "+00:00"))
        assert (paused_at if paused_at.tzinfo else paused_at.replace(tzinfo=UTC)) == expires_at
        assert [h["action"] for h in body["pause_history"]] == ["start", "expire"]

        with Session(_session_manager.engine) as session:
            stored = session.get(TimerSession, UUID(timer_id))
            assert (stored.status, stored.elapsed_time, stored.paused_at, stored.updated_at) == (
                "RUNNING", 0, None, STORED_UPDATED_AT
            )
            assert [h["action"] for h in stored.pause_history] == ["start"]
