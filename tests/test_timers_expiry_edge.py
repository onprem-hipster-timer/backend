"""
타이머 만료 경계 테스트

- 재개한 뒤 만료되면 만료 시각은 재개 시각 + (allocated - 저장된 elapsed)
- 친구의 공유 조회와 /v1/todos/{id}/timers 경로도 만료 표현을 보인다
- 만료 타이머에 다른 필드를 PATCH해도 만료가 확정된다 (expire → update)
- timezone 변환은 가상 expire 이력에도 적용된다
- status 필터는 저장된 상태 기준이다
- expire 이벤트 페이로드는 만료 표현을 담는다

기본 동작은 tests/test_timers_expiry.py.
"""
from datetime import datetime, timedelta, UTC
from uuid import UUID

import pytest
from sqlalchemy import update
from sqlmodel import Session

from app.db.session import _session_manager
from app.domain.timer.model import TimerSession

ALLOCATED = 60


def _create(client, **body) -> dict:
    response = client.post("/v1/timers", json={"title": "만료 타이머", "allocated_duration": ALLOCATED, **body})
    assert response.status_code == 201, response.text
    return response.json()


def _set(timer_id: str, **values) -> None:
    with Session(_session_manager.engine) as session:
        session.execute(update(TimerSession).where(TimerSession.id == UUID(timer_id)).values(**values))
        session.commit()


def _ago(seconds: int) -> datetime:
    return datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=seconds)


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)).replace(microsecond=0)


def _make_friends(client_a, client_b) -> None:
    friend_code = client_b.get("/v1/users/me").json()["friend_code"]
    assert client_a.post("/v1/friends/requests", json={"friend_code": friend_code}).status_code == 201
    friendship_id = client_b.get("/v1/friends/requests/received").json()[0]["id"]
    assert client_b.post(f"/v1/friends/requests/{friendship_id}/accept").status_code == 200


@pytest.mark.e2e
def test_expiry_after_resume_uses_stored_elapsed(e2e_client):
    """일시정지(elapsed 20) 뒤 재개하고 50초가 지나면 만료. 만료 시각은 재개 + 40초"""
    timer_id = _create(e2e_client)["id"]
    _set(timer_id, started_at=_ago(20))
    paused = e2e_client.patch(f"/v1/timers/{timer_id}/pause").json()
    assert 20 <= paused["elapsed_time"] < 25
    stored_elapsed = paused["elapsed_time"]

    assert e2e_client.patch(f"/v1/timers/{timer_id}/resume").status_code == 200
    resumed_at = _ago(50)
    _set(timer_id, started_at=resumed_at)

    body = e2e_client.get(f"/v1/timers/{timer_id}").json()

    assert body["status"] == "PAUSED"
    assert body["elapsed_time"] == ALLOCATED
    expected = (resumed_at + timedelta(seconds=ALLOCATED - stored_elapsed)).replace(tzinfo=UTC, microsecond=0)
    assert _utc(body["paused_at"]) == expected
    assert [h["action"] for h in body["pause_history"]] == ["start", "pause", "resume", "expire"]


@pytest.mark.e2e
def test_not_expired_one_second_before_after_resume(e2e_client):
    timer_id = _create(e2e_client)["id"]
    _set(timer_id, started_at=_ago(20))
    e2e_client.patch(f"/v1/timers/{timer_id}/pause")
    e2e_client.patch(f"/v1/timers/{timer_id}/resume")
    _set(timer_id, started_at=_ago(ALLOCATED - 20 - 5))

    body = e2e_client.get(f"/v1/timers/{timer_id}").json()

    assert body["status"] == "RUNNING"


@pytest.mark.e2e
def test_friend_sees_expired_shared_timer(multi_user_e2e):
    owner = multi_user_e2e.as_user("owner")
    friend = multi_user_e2e.as_user("friend")
    _make_friends(owner, friend)
    timer_id = _create(owner)["id"]
    assert owner.put(f"/v1/visibility/timer/{timer_id}", json={"level": "friends"}).status_code == 200
    _set(timer_id, started_at=_ago(ALLOCATED + 30))

    single = friend.get(f"/v1/timers/{timer_id}").json()
    shared = friend.get("/v1/timers", params={"scope": "shared"}).json()

    assert single["status"] == "PAUSED"
    assert single["elapsed_time"] == ALLOCATED
    assert single["is_shared"] is True
    [listed] = [t for t in shared if t["id"] == timer_id]
    assert listed["status"] == "PAUSED"
    assert listed["elapsed_time"] == ALLOCATED


@pytest.mark.e2e
def test_todo_timers_path_shows_expiry(e2e_client):
    group = e2e_client.post("/v1/tags/groups", json={"name": "그룹", "color": "#FF5733"}).json()
    todo = e2e_client.post("/v1/todos", json={"title": "할 일", "tag_group_id": group["id"]}).json()
    timer_id = _create(e2e_client, todo_id=todo["id"])["id"]
    _set(timer_id, started_at=_ago(ALLOCATED + 30))

    listed = e2e_client.get(f"/v1/todos/{todo['id']}/timers").json()
    active = e2e_client.get(f"/v1/todos/{todo['id']}/timers/active")

    [body] = [t for t in listed if t["id"] == timer_id]
    assert body["status"] == "PAUSED"
    assert body["elapsed_time"] == ALLOCATED
    assert active.status_code == 200
    assert active.json()["status"] == "PAUSED"


@pytest.mark.e2e
def test_patch_title_on_expired_timer_materializes(e2e_client, after_commit_items):
    timer_id = _create(e2e_client)["id"]
    _set(timer_id, started_at=_ago(ALLOCATED + 30))
    after_commit_items.clear()

    response = e2e_client.patch(f"/v1/timers/{timer_id}", json={"title": "바뀐 제목"})

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "바뀐 제목"
    assert body["status"] == "PAUSED"
    assert body["elapsed_time"] == ALLOCATED
    assert [h["action"] for h in body["pause_history"]] == ["start", "expire"]
    with Session(_session_manager.engine) as session:
        assert session.get(TimerSession, UUID(timer_id)).status == "PAUSED"
    assert [i["message"]["payload"]["action"] for i in after_commit_items] == ["expire", "update"]


@pytest.mark.e2e
def test_timezone_applies_to_virtual_expire_entry(e2e_client):
    timer_id = _create(e2e_client)["id"]
    started_at = _ago(ALLOCATED + 30)
    _set(timer_id, started_at=started_at)

    body = e2e_client.get(f"/v1/timers/{timer_id}", params={"timezone": "Asia/Seoul"}).json()

    seoul = timedelta(hours=9)
    assert datetime.fromisoformat(body["paused_at"]).utcoffset() == seoul
    expire = body["pause_history"][-1]
    assert expire["action"] == "expire"
    assert datetime.fromisoformat(expire["at"]).utcoffset() == seoul
    assert _utc(expire["at"]) == _utc(body["paused_at"])
    assert datetime.fromisoformat(body["pause_history"][0]["at"]).utcoffset() == seoul


@pytest.mark.e2e
def test_status_filter_uses_stored_status(e2e_client):
    timer_id = _create(e2e_client)["id"]
    _set(timer_id, started_at=_ago(ALLOCATED + 30))

    running = e2e_client.get("/v1/timers", params={"status": "RUNNING"}).json()
    paused = e2e_client.get("/v1/timers", params={"status": "PAUSED"}).json()

    [body] = [t for t in running if t["id"] == timer_id]
    assert body["status"] == "PAUSED"
    assert timer_id not in {t["id"] for t in paused}


@pytest.mark.e2e
def test_expire_event_payload_carries_expired_fields(e2e_client, after_commit_items):
    timer_id = _create(e2e_client)["id"]
    started_at = _ago(ALLOCATED + 30)
    _set(timer_id, started_at=started_at)
    after_commit_items.clear()

    e2e_client.patch(f"/v1/timers/{timer_id}/pause")

    [item] = after_commit_items
    timer = item["message"]["payload"]["timer"]
    assert timer["elapsed_time"] == ALLOCATED
    assert _utc(timer["paused_at"]) == (started_at + timedelta(seconds=ALLOCATED)).replace(tzinfo=UTC, microsecond=0)
    assert timer["pause_history"][-1]["action"] == "expire"


@pytest.mark.e2e
def test_delete_expired_timer(e2e_client):
    timer_id = _create(e2e_client)["id"]
    _set(timer_id, started_at=_ago(ALLOCATED + 30))

    assert e2e_client.delete(f"/v1/timers/{timer_id}").status_code == 200
    assert e2e_client.get(f"/v1/timers/{timer_id}").status_code == 404
