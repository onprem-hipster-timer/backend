"""
TimerService 실시간 이벤트 테스트 (app/domain/timer/realtime.py)

이벤트는 커밋된 뒤에만 sink로 넘어가므로 실제로 커밋하는 세션을 쓴다.
"""
from datetime import datetime, timedelta, UTC
from uuid import UUID

import pytest
from sqlalchemy import update
from sqlmodel import Session

from app.domain.friend.service import FriendService
from app.domain.timer.model import TimerSession
from app.domain.timer.schema.dto import TimerCreate, TimerUpdate
from app.domain.timer.service import TimerService
from app.domain.visibility.enums import ResourceType, VisibilityLevel
from app.domain.visibility.service import VisibilityService
from tests.conftest import make_user

OWNER = make_user("owner", name="Owner Name")
FRIEND = make_user("friend")
OTHER_FRIEND = make_user("other-friend")


@pytest.fixture
def session(test_engine):
    with Session(test_engine) as session:
        yield session


@pytest.fixture
def friends(session):
    owner_friends = FriendService(session, OWNER)
    for friend in (FRIEND, OTHER_FRIEND):
        request = owner_friends.send_friend_request(friend.sub)
        FriendService(session, friend).accept_friend_request(request.id)
    session.commit()


def _create(session) -> TimerSession:
    timer = TimerService(session, OWNER).create_timer(TimerCreate(title="실시간", allocated_duration=1800))
    session.commit()
    return timer


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _assert_utc(value: str) -> None:
    assert _parse(value).utcoffset() == timedelta(0)


def test_create_sends_created_event_to_owner_after_commit(session, after_commit_items):
    timer = TimerService(session, OWNER).create_timer(TimerCreate(title="실시간", allocated_duration=1800))
    assert after_commit_items == []

    session.commit()

    assert len(after_commit_items) == 1
    item = after_commit_items[0]
    assert item["users"] == {OWNER.sub}
    message = item["message"]
    assert UUID(message["id"])
    assert message["type"] == "timer.created"
    assert message["from_user"] == OWNER.sub
    _assert_utc(message["timestamp"])
    payload = message["payload"]
    assert payload["action"] == "start"
    assert payload["actor_name"] == "Owner Name"
    assert payload["timer"]["id"] == str(timer.id)
    assert payload["timer"]["status"] == "RUNNING"
    for field in ("started_at", "created_at", "updated_at"):
        _assert_utc(payload["timer"][field])
    _assert_utc(payload["timer"]["pause_history"][0]["at"])


@pytest.mark.parametrize("method, action, status", [
    ("pause_timer", "pause", "PAUSED"),
    ("stop_timer", "stop", "COMPLETED"),
    ("cancel_timer", "cancel", "CANCELLED"),
])
def test_commands_send_updated_event(session, after_commit_items, method, action, status):
    timer = _create(session)
    after_commit_items.clear()

    getattr(TimerService(session, OWNER), method)(timer.id)
    session.commit()

    [item] = after_commit_items
    assert item["message"]["type"] == "timer.updated"
    assert item["message"]["payload"]["action"] == action
    assert item["message"]["payload"]["timer"]["status"] == status


def test_resume_and_update_send_updated_event(session, after_commit_items):
    timer = _create(session)
    service = TimerService(session, OWNER)
    service.pause_timer(timer.id)
    session.commit()
    after_commit_items.clear()

    service.resume_timer(timer.id)
    service.update_timer(timer.id, TimerUpdate(title="새 제목"))
    session.commit()

    actions = [item["message"]["payload"]["action"] for item in after_commit_items]
    assert actions == ["resume", "update"]
    assert after_commit_items[1]["message"]["payload"]["timer"]["title"] == "새 제목"


def test_event_carries_stored_elapsed_time(session, test_engine, after_commit_items):
    """이벤트의 elapsed_time은 커밋된 저장값과 같다 (RUNNING 구간은 클라이언트가 더한다)"""
    timer = _create(session)
    session.execute(
        update(TimerSession)
        .where(TimerSession.id == timer.id)
        .values(started_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=120))
    )
    session.commit()
    after_commit_items.clear()

    service = TimerService(session, OWNER)
    service.pause_timer(timer.id)
    service.resume_timer(timer.id)
    session.commit()

    with Session(test_engine) as fresh:
        stored = fresh.get(TimerSession, timer.id).elapsed_time
    assert stored >= 120
    assert [item["message"]["payload"]["timer"]["elapsed_time"] for item in after_commit_items] == [stored, stored]


@pytest.mark.parametrize("level, kwargs, expected", [
    (VisibilityLevel.PRIVATE, {}, {"owner"}),
    (VisibilityLevel.FRIENDS, {}, {"owner", "friend", "other-friend"}),
    (VisibilityLevel.SELECTED_FRIENDS, {"allowed_user_ids": ["friend"]}, {"owner", "friend"}),
])
def test_recipients_follow_visibility(session, friends, after_commit_items, level, kwargs, expected):
    timer = _create(session)
    VisibilityService(session, OWNER).set_visibility(ResourceType.TIMER, timer.id, level, **kwargs)
    session.commit()
    after_commit_items.clear()

    TimerService(session, OWNER).pause_timer(timer.id)
    session.commit()

    assert after_commit_items[0]["users"] == expected


def test_delete_sends_tombstone_to_recipients_before_visibility_removed(session, friends, after_commit_items):
    timer = _create(session)
    timer_id = timer.id
    VisibilityService(session, OWNER).set_visibility(ResourceType.TIMER, timer_id, VisibilityLevel.FRIENDS)
    session.commit()
    after_commit_items.clear()

    TimerService(session, OWNER).delete_timer(timer_id)
    session.commit()

    [item] = after_commit_items
    assert item["users"] == {"owner", "friend", "other-friend"}
    message = item["message"]
    assert message["type"] == "timer.deleted"
    assert message["payload"]["action"] == "delete"
    assert message["payload"]["timer"] is None
    assert message["payload"]["timer_id"] == str(timer_id)


def test_rollback_sends_nothing(session, after_commit_items):
    timer = _create(session)
    after_commit_items.clear()

    TimerService(session, OWNER).pause_timer(timer.id)
    session.rollback()

    assert after_commit_items == []


@pytest.mark.e2e
def test_event_datetimes_equal_rest_response(e2e_client, after_commit_items):
    """같은 상태면 이벤트와 REST 응답(timezone=UTC)의 시각 문자열이 같다 (updated_at 비교가 맞게)"""
    created = e2e_client.post(
        "/v1/timers", params={"timezone": "UTC"}, json={"title": "형식", "allocated_duration": 60}
    ).json()
    paused = e2e_client.patch(f"/v1/timers/{created['id']}/pause", params={"timezone": "UTC"}).json()
    fetched = e2e_client.get(f"/v1/timers/{created['id']}", params={"timezone": "UTC"}).json()

    events = [item["message"] for item in after_commit_items]
    assert len(events) == 2
    for response, event in zip([created, paused], events):
        timer = event["payload"]["timer"]
        for field in ("started_at", "paused_at", "ended_at", "created_at", "updated_at"):
            assert timer[field] == response[field], field
        assert timer["pause_history"] == response["pause_history"]
        assert datetime.strptime(event["timestamp"], "%Y-%m-%dT%H:%M:%S%z").utcoffset() == timedelta(0)
    assert events[-1]["payload"]["timer"]["updated_at"] == fetched["updated_at"]
