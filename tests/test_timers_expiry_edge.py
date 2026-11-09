"""
타이머 만료 경계 테스트

- 재개한 뒤 만료되면 만료 시각은 재개 시각 + (allocated - 저장된 elapsed)
- 친구의 공유 조회와 /v1/todos/{id}/timers 경로도 만료 표현을 보인다
- 만료 타이머에 다른 필드를 PATCH해도 만료가 확정된다 (expire → update)
- timezone 변환은 가상 expire 이력에도 적용된다
- status 필터는 저장된 상태 기준이다
- expire 이벤트 페이로드는 만료 표현을 담는다
- Todo 변경은 할당 시간을 다 쓴 타이머에만 expire를 앞세우고, 한 번만 확정한다
- allocated_duration이 현재 경과 시간과 같으면 422. 400인 resume과 422인 PATCH는 만료 타이머를 저장하지 않는다
- 데이터 이전으로 allocated == elapsed가 된 기존 행의 연장·만료

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


def _timer_actions(items: list[dict], timer_id: str) -> list[str]:
    return [
        item["message"]["payload"]["action"] for item in items
        if item["message"]["type"].startswith("timer.")
        and (item["message"]["payload"].get("timer") or {}).get("id") == timer_id
    ]


def _todo(client) -> dict:
    group = client.post("/v1/tags/groups", json={"name": "그룹", "color": "#FF5733"}).json()
    return client.post("/v1/todos", json={"title": "할 일", "tag_group_id": group["id"]}).json()


@pytest.mark.e2e
@pytest.mark.parametrize("ran, expired", [(ALLOCATED - 2, False), (ALLOCATED, True)])
def test_todo_change_at_expiry_boundary(e2e_client, after_commit_items, ran, expired):
    """Todo 변경 시점에 할당 시간을 다 썼을 때만 expire가 앞선다"""
    todo = _todo(e2e_client)
    timer_id = _create(e2e_client, todo_id=todo["id"])["id"]
    _set(timer_id, started_at=_ago(ran))
    after_commit_items.clear()

    assert e2e_client.patch(f"/v1/todos/{todo['id']}", json={"deadline": "2024-01-20T10:00:00Z"}).status_code == 200

    assert _timer_actions(after_commit_items, timer_id) == (["expire", "update"] if expired else ["update"])
    with Session(_session_manager.engine) as session:
        stored = session.get(TimerSession, UUID(timer_id))
        assert stored.status == ("PAUSED" if expired else "RUNNING")
        assert stored.elapsed_time == (ALLOCATED if expired else 0)


@pytest.mark.e2e
@pytest.mark.parametrize("todo_status, action", [("DONE", "stop"), ("CANCELLED", "cancel")])
def test_todo_status_on_running_timer_before_expiry_has_no_expire(e2e_client, after_commit_items, todo_status, action):
    todo = _todo(e2e_client)
    timer_id = _create(e2e_client, todo_id=todo["id"])["id"]
    _set(timer_id, started_at=_ago(ALLOCATED - 20))
    after_commit_items.clear()

    assert e2e_client.patch(f"/v1/todos/{todo['id']}", json={"status": todo_status}).status_code == 200

    assert _timer_actions(after_commit_items, timer_id) == [action]
    body = e2e_client.get(f"/v1/timers/{timer_id}").json()
    assert [h["action"] for h in body["pause_history"]] == ["start", action]
    assert body["elapsed_time"] < ALLOCATED


@pytest.mark.e2e
@pytest.mark.parametrize("todo_status, action", [("DONE", "stop"), ("CANCELLED", "cancel")])
def test_todo_status_on_user_paused_timer_long_ago_has_no_expire(e2e_client, after_commit_items, todo_status, action):
    """사용자가 멈춘 타이머는 오래 지나도 Todo 상태 변경에 expire가 붙지 않는다"""
    todo = _todo(e2e_client)
    timer_id = _create(e2e_client, todo_id=todo["id"])["id"]
    _set(timer_id, started_at=_ago(10))
    elapsed = e2e_client.patch(f"/v1/timers/{timer_id}/pause").json()["elapsed_time"]
    _set(timer_id, paused_at=_ago(ALLOCATED * 10), started_at=_ago(ALLOCATED * 10 + elapsed))
    after_commit_items.clear()

    assert e2e_client.patch(f"/v1/todos/{todo['id']}", json={"status": todo_status}).status_code == 200

    assert _timer_actions(after_commit_items, timer_id) == [action]
    body = e2e_client.get(f"/v1/timers/{timer_id}").json()
    assert body["elapsed_time"] == elapsed
    assert "expire" not in [h["action"] for h in body["pause_history"]]


@pytest.mark.e2e
def test_repeated_linked_change_materializes_once(e2e_client, after_commit_items):
    todo = _todo(e2e_client)
    timer_id = _create(e2e_client, todo_id=todo["id"])["id"]
    _set(timer_id, started_at=_ago(ALLOCATED + 30))
    after_commit_items.clear()

    for deadline in ("2024-01-20T10:00:00Z", "2024-01-21T10:00:00Z"):
        assert e2e_client.patch(f"/v1/todos/{todo['id']}", json={"deadline": deadline}).status_code == 200
    assert e2e_client.patch(f"/v1/timers/{timer_id}/pause").status_code in (200, 400)

    assert _timer_actions(after_commit_items, timer_id).count("expire") == 1
    with Session(_session_manager.engine) as session:
        actions = [h["action"] for h in session.get(TimerSession, UUID(timer_id)).pause_history]
    assert actions == ["start", "expire"]


@pytest.mark.e2e
def test_patch_equal_to_used_is_422_and_one_above_keeps_running(e2e_client):
    timer_id = e2e_client.post("/v1/timers", json={"title": "경계", "allocated_duration": 1500}).json()["id"]
    _set(timer_id, started_at=_ago(100))

    response = e2e_client.patch(f"/v1/timers/{timer_id}", json={"allocated_duration": 100})
    assert response.status_code == 422
    assert response.json()["error_type"] == "AllocatedDurationTooShortError"

    response = e2e_client.patch(f"/v1/timers/{timer_id}", json={"allocated_duration": 102})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "RUNNING"
    assert response.json()["elapsed_time"] == 0


@pytest.mark.e2e
def test_patch_equal_to_paused_elapsed_is_422(e2e_client, after_commit_items):
    timer_id = _create(e2e_client)["id"]
    _set(timer_id, started_at=_ago(20))
    elapsed = e2e_client.patch(f"/v1/timers/{timer_id}/pause").json()["elapsed_time"]
    after_commit_items.clear()

    response = e2e_client.patch(f"/v1/timers/{timer_id}", json={"allocated_duration": elapsed})
    assert response.status_code == 422
    assert after_commit_items == []
    response = e2e_client.patch(f"/v1/timers/{timer_id}", json={"allocated_duration": elapsed + 1})
    assert response.status_code == 200


@pytest.mark.e2e
def test_migrated_paused_overrun_row_extends_and_resumes(e2e_client):
    """이전으로 allocated == elapsed가 된 PAUSED 행은 +300 연장 뒤 재개된다"""
    timer_id = e2e_client.post("/v1/timers", json={"title": "기존", "allocated_duration": 1500}).json()["id"]
    e2e_client.patch(f"/v1/timers/{timer_id}/pause")
    _set(timer_id, allocated_duration=2400, elapsed_time=2400)

    response = e2e_client.patch(f"/v1/timers/{timer_id}", json={"allocated_duration": 2700})
    assert response.status_code == 200, response.text
    assert response.json()["allocated_duration"] == 2700
    resumed = e2e_client.patch(f"/v1/timers/{timer_id}/resume")
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "RUNNING"


@pytest.mark.e2e
def test_migrated_running_overrun_row_expires_at_last_resume(e2e_client, after_commit_items):
    """이전으로 allocated == elapsed가 된 RUNNING 행은 마지막 재개 시각에 만료로 읽히고 elapsed를 지킨다"""
    timer_id = e2e_client.post("/v1/timers", json={"title": "기존", "allocated_duration": 1500}).json()["id"]
    resumed_at = _ago(10)
    _set(
        timer_id, allocated_duration=2400, elapsed_time=2400, started_at=resumed_at,
        pause_history=[
            {"action": "start", "at": _ago(5000).isoformat()},
            {"action": "pause", "at": _ago(100).isoformat(), "elapsed": 2400},
            {"action": "resume", "at": resumed_at.isoformat()},
        ],
    )

    body = e2e_client.get(f"/v1/timers/{timer_id}").json()
    assert body["status"] == "PAUSED"
    assert body["elapsed_time"] == 2400
    assert _utc(body["paused_at"]) == _utc(body["started_at"])

    after_commit_items.clear()
    stopped = e2e_client.post(f"/v1/timers/{timer_id}/stop")
    assert stopped.status_code == 200
    assert stopped.json()["elapsed_time"] == 2400
    assert _timer_actions(after_commit_items, timer_id) == ["expire", "stop"]


@pytest.mark.e2e
def test_timezone_applies_to_materialized_expiry(e2e_client):
    """Todo 변경으로 확정된 만료 필드도 timezone 변환을 받는다"""
    todo = _todo(e2e_client)
    timer_id = _create(e2e_client, todo_id=todo["id"])["id"]
    started_at = _ago(ALLOCATED + 30)
    _set(timer_id, started_at=started_at)
    e2e_client.patch(f"/v1/todos/{todo['id']}", json={"deadline": "2024-01-20T10:00:00Z"})
    with Session(_session_manager.engine) as session:
        assert session.get(TimerSession, UUID(timer_id)).status == "PAUSED"

    body = e2e_client.get(f"/v1/timers/{timer_id}", params={"timezone": "Asia/Seoul"}).json()

    seoul = timedelta(hours=9)
    expected = (started_at + timedelta(seconds=ALLOCATED)).replace(tzinfo=UTC, microsecond=0)
    assert datetime.fromisoformat(body["paused_at"]).utcoffset() == seoul
    assert _utc(body["paused_at"]) == expected
    expire = body["pause_history"][-1]
    assert expire["action"] == "expire"
    assert datetime.fromisoformat(expire["at"]).utcoffset() == seoul
    assert _utc(expire["at"]) == expected


@pytest.mark.e2e
def test_failed_resume_and_patch_on_expired_timer_store_nothing(e2e_client, after_commit_items):
    timer_id = _create(e2e_client)["id"]
    _set(timer_id, started_at=_ago(ALLOCATED + 30))
    after_commit_items.clear()

    assert e2e_client.patch(f"/v1/timers/{timer_id}/resume").status_code == 400
    response = e2e_client.patch(f"/v1/timers/{timer_id}", json={"allocated_duration": ALLOCATED, "title": "바뀌지 않음"})
    assert response.status_code == 422

    assert after_commit_items == []
    with Session(_session_manager.engine) as session:
        stored = session.get(TimerSession, UUID(timer_id))
        assert stored.status == "RUNNING"
        assert stored.title == "만료 타이머"
        assert [h["action"] for h in stored.pause_history] == ["start"]
