"""
타이머 만료 테스트

- elapsed_time은 allocated_duration을 넘지 않는다 (stop, pause, Todo DONE 전파)
- 명령(pause·resume·stop·cancel)은 만료를 행에 확정하고 expire 이벤트를 보낸다
- 만료로 멈춘 타이머는 재개할 수 없다. PATCH로 allocated_duration을 늘리면 재개할 수 있다
- allocated_duration은 elapsed_time보다 커야 한다 (422)
- 사용자가 멈춘 타이머는 만료되지 않는다

조회가 행을 쓰지 않는 것은 tests/test_timers_read_no_write.py.
시각은 started_at을 DB에 직접 과거로 기록해 흘려보낸다.
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


def _parse_utc(value: str) -> datetime:
    """응답 시각(초 단위 직렬화)을 UTC aware로"""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)).replace(microsecond=0)


def _stored(timer_id: str) -> TimerSession:
    with Session(_session_manager.engine) as session:
        return session.get(TimerSession, UUID(timer_id))


def _expired_timer(client, **body) -> tuple[str, datetime]:
    """할당 시간을 넘긴 RUNNING 타이머의 ID와 만료 시각(UTC aware, 초 단위)"""
    timer_id = _create(client, **body)["id"]
    started_at = _backdate(timer_id, ALLOCATED + 30)
    return timer_id, (started_at + timedelta(seconds=ALLOCATED)).replace(tzinfo=UTC, microsecond=0)


def _assert_expired(body: dict, expires_at: datetime) -> None:
    assert body["status"] == "PAUSED"
    assert body["elapsed_time"] == ALLOCATED
    assert _parse_utc(body["paused_at"]) == expires_at
    assert body["pause_history"][-1]["action"] == "expire"
    assert _parse_utc(body["pause_history"][-1]["at"]) == expires_at
    assert body["pause_history"][-1]["elapsed"] == ALLOCATED


def _backdate(timer_id: str, seconds: int) -> datetime:
    """started_at을 seconds초 전으로 DB에 직접 기록하고 그 값을 반환"""
    started_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=seconds)
    with Session(_session_manager.engine) as session:
        session.execute(
            update(TimerSession).where(TimerSession.id == UUID(timer_id)).values(started_at=started_at)
        )
        session.commit()
    return started_at


@pytest.mark.e2e
@pytest.mark.parametrize("action", ["pause", "stop"])
def test_elapsed_is_capped_at_allocated(e2e_client, action):
    timer_id = _create(e2e_client)["id"]
    _backdate(timer_id, ALLOCATED * 10)

    method = e2e_client.post if action == "stop" else e2e_client.patch
    response = method(f"/v1/timers/{timer_id}/{action}")

    assert response.status_code == 200
    assert response.json()["elapsed_time"] == ALLOCATED


@pytest.mark.e2e
def test_todo_done_long_after_expiry_completes_with_allocated(e2e_client, after_commit_items):
    group = e2e_client.post("/v1/tags/groups", json={"name": "그룹", "color": "#FF5733"}).json()
    todo = e2e_client.post("/v1/todos", json={"title": "할 일", "tag_group_id": group["id"]}).json()
    timer_id = _create(e2e_client, todo_id=todo["id"])["id"]
    _backdate(timer_id, ALLOCATED * 10)
    after_commit_items.clear()

    response = e2e_client.patch(f"/v1/todos/{todo['id']}", json={"status": "DONE"})

    assert response.status_code == 200, response.text
    timer = e2e_client.get(f"/v1/timers/{timer_id}").json()
    assert timer["status"] == "COMPLETED"
    assert timer["elapsed_time"] == ALLOCATED
    assert [h["action"] for h in timer["pause_history"]] == ["start", "expire", "stop"]
    assert [i["message"]["payload"]["action"] for i in after_commit_items] == ["expire", "stop"]


@pytest.mark.e2e
@pytest.mark.parametrize("todo_status, action", [("DONE", "stop"), ("CANCELLED", "cancel")])
def test_todo_status_finishes_expired_timer_like_endpoint(e2e_client, after_commit_items, todo_status, action):
    """Todo 상태로 끝낸 만료 타이머와 stop·cancel로 끝낸 만료 타이머는 elapsed·이력·이벤트가 같다"""
    group = e2e_client.post("/v1/tags/groups", json={"name": "그룹", "color": "#FF5733"}).json()
    todo = e2e_client.post("/v1/todos", json={"title": "할 일", "tag_group_id": group["id"]}).json()
    via_todo, todo_expires_at = _expired_timer(e2e_client, todo_id=todo["id"])
    via_endpoint, endpoint_expires_at = _expired_timer(e2e_client)

    after_commit_items.clear()
    assert e2e_client.patch(f"/v1/todos/{todo['id']}", json={"status": todo_status}).status_code == 200
    todo_events = [i["message"]["payload"]["action"] for i in after_commit_items]
    after_commit_items.clear()
    assert e2e_client.post(f"/v1/timers/{via_endpoint}/{action}").status_code == 200
    endpoint_events = [i["message"]["payload"]["action"] for i in after_commit_items]

    for timer_id, expires_at, events in (
            (via_todo, todo_expires_at, todo_events),
            (via_endpoint, endpoint_expires_at, endpoint_events),
    ):
        body = e2e_client.get(f"/v1/timers/{timer_id}").json()
        assert body["elapsed_time"] == ALLOCATED
        assert [h["action"] for h in body["pause_history"]] == ["start", "expire", action]
        assert _parse_utc(body["pause_history"][1]["at"]) == expires_at
        assert body["pause_history"][2]["elapsed"] == ALLOCATED
        assert events == ["expire", action]


@pytest.mark.e2e
def test_running_before_expiry_pauses_normally(e2e_client):
    timer_id = _create(e2e_client)["id"]
    _backdate(timer_id, ALLOCATED - 2)

    assert e2e_client.get(f"/v1/timers/{timer_id}").json()["status"] == "RUNNING"
    paused = e2e_client.patch(f"/v1/timers/{timer_id}/pause").json()

    assert paused["status"] == "PAUSED"
    assert ALLOCATED - 2 <= paused["elapsed_time"] < ALLOCATED
    assert paused["pause_history"][-1]["action"] == "pause"


@pytest.mark.e2e
def test_pause_after_expiry_materializes_expiry(e2e_client, after_commit_items):
    timer_id, expires_at = _expired_timer(e2e_client)
    after_commit_items.clear()

    response = e2e_client.patch(f"/v1/timers/{timer_id}/pause")

    assert response.status_code == 200
    _assert_expired(response.json(), expires_at)
    assert [h["action"] for h in response.json()["pause_history"]] == ["start", "expire"]
    assert _stored(timer_id).status == "PAUSED"
    [item] = after_commit_items
    assert item["message"]["payload"]["action"] == "expire"
    assert item["message"]["payload"]["timer"]["status"] == "PAUSED"


@pytest.mark.e2e
def test_second_pause_after_expiry_is_200(e2e_client, after_commit_items):
    timer_id, expires_at = _expired_timer(e2e_client)
    assert e2e_client.patch(f"/v1/timers/{timer_id}/pause").status_code == 200
    after_commit_items.clear()

    response = e2e_client.patch(f"/v1/timers/{timer_id}/pause")

    assert response.status_code == 200
    _assert_expired(response.json(), expires_at)
    assert after_commit_items == []


@pytest.mark.e2e
def test_stop_after_expiry_completes_with_allocated(e2e_client, after_commit_items):
    group = e2e_client.post("/v1/tags/groups", json={"name": "그룹", "color": "#FF5733"}).json()
    todo = e2e_client.post("/v1/todos", json={"title": "할 일", "tag_group_id": group["id"]}).json()
    timer_id = _create(e2e_client, todo_id=todo["id"])["id"]
    _backdate(timer_id, ALLOCATED + 30)
    after_commit_items.clear()

    response = e2e_client.post(f"/v1/timers/{timer_id}/stop", params={"include_todo": True})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "COMPLETED"
    assert body["elapsed_time"] == ALLOCATED
    assert [h["action"] for h in body["pause_history"]] == ["start", "expire", "stop"]
    assert body["todo"]["status"] == "DONE"
    actions = [item["message"]["payload"]["action"] for item in after_commit_items]
    assert actions[:2] == ["expire", "stop"]


@pytest.mark.e2e
def test_cancel_after_expiry_keeps_allocated(e2e_client):
    timer_id, _ = _expired_timer(e2e_client)

    response = e2e_client.post(f"/v1/timers/{timer_id}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"
    assert response.json()["elapsed_time"] == ALLOCATED
    assert [h["action"] for h in response.json()["pause_history"]] == ["start", "expire", "cancel"]


@pytest.mark.e2e
def test_resume_after_expiry_is_400(e2e_client, after_commit_items):
    timer_id, _ = _expired_timer(e2e_client)
    after_commit_items.clear()

    response = e2e_client.patch(f"/v1/timers/{timer_id}/resume")

    assert response.status_code == 400
    assert "allocated_duration" in response.text
    assert after_commit_items == []


@pytest.mark.e2e
def test_user_paused_timer_does_not_expire(e2e_client):
    timer_id = _create(e2e_client)["id"]
    paused = e2e_client.patch(f"/v1/timers/{timer_id}/pause").json()
    with Session(_session_manager.engine) as session:
        session.execute(
            update(TimerSession)
            .where(TimerSession.id == UUID(timer_id))
            .values(
                started_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=ALLOCATED * 10),
                paused_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=ALLOCATED * 9),
            )
        )
        session.commit()

    body = e2e_client.get(f"/v1/timers/{timer_id}").json()

    assert body["status"] == "PAUSED"
    assert body["elapsed_time"] == paused["elapsed_time"]
    assert body["pause_history"][-1]["action"] == "pause"
    assert e2e_client.patch(f"/v1/timers/{timer_id}/pause").status_code == 400
    assert e2e_client.patch(f"/v1/timers/{timer_id}/resume").json()["status"] == "RUNNING"


@pytest.mark.e2e
def test_extend_expired_timer_then_resume(e2e_client):
    timer_id, _ = _expired_timer(e2e_client)
    assert e2e_client.patch(f"/v1/timers/{timer_id}/resume").status_code == 400

    extended = e2e_client.patch(f"/v1/timers/{timer_id}", json={"allocated_duration": ALLOCATED + 600})
    assert extended.status_code == 200, extended.text
    assert extended.json()["allocated_duration"] == ALLOCATED + 600
    assert extended.json()["status"] == "PAUSED"
    assert extended.json()["elapsed_time"] == ALLOCATED

    resumed = e2e_client.patch(f"/v1/timers/{timer_id}/resume")
    assert resumed.status_code == 200
    body = resumed.json()
    assert body["status"] == "RUNNING"
    assert _parse_utc(body["started_at"]) >= _parse_utc(extended.json()["paused_at"])

    current = e2e_client.get(f"/v1/timers/{timer_id}").json()
    assert current["status"] == "RUNNING"
    assert current["allocated_duration"] - current["elapsed_time"] > 0


@pytest.mark.e2e
@pytest.mark.parametrize("expired", [False, True])
def test_allocated_duration_not_above_elapsed_is_422(e2e_client, expired):
    if expired:
        timer_id, _ = _expired_timer(e2e_client)
        too_short = ALLOCATED
    else:
        timer_id = _create(e2e_client)["id"]
        e2e_client.patch(f"/v1/timers/{timer_id}/pause")
        too_short = 0

    response = e2e_client.patch(f"/v1/timers/{timer_id}", json={"allocated_duration": too_short})

    assert response.status_code == 422
    assert response.json()["error_type"] == "AllocatedDurationTooShortError"
    assert _stored(timer_id).allocated_duration == ALLOCATED


@pytest.mark.e2e
def test_extend_running_timer_before_expiry(e2e_client):
    timer_id = _create(e2e_client)["id"]

    response = e2e_client.patch(f"/v1/timers/{timer_id}", json={"allocated_duration": ALLOCATED * 2})

    assert response.status_code == 200
    assert response.json()["status"] == "RUNNING"
    assert response.json()["allocated_duration"] == ALLOCATED * 2


def _timer_events(items: list[dict], timer_id: str) -> list[dict]:
    return [
        item["message"]["payload"] for item in items
        if item["message"]["type"].startswith("timer.")
        and (item["message"]["payload"].get("timer") or {}).get("id") == timer_id
    ]


@pytest.mark.e2e
@pytest.mark.parametrize("path", ["todo_deadline", "todo_unlink", "schedule_unlink"])
def test_linked_resource_change_materializes_expiry_first(e2e_client, after_commit_items, path):
    """Todo·Schedule 쪽 변경이 보내는 update 앞에 만료가 확정되고, 두 페이로드 모두 PAUSED"""
    if path == "schedule_unlink":
        schedule = e2e_client.post(
            "/v1/schedules",
            json={"title": "일정", "start_time": "2024-01-01T10:00:00Z", "end_time": "2024-01-01T12:00:00Z"},
        ).json()
        timer_id, expires_at = _expired_timer(e2e_client, schedule_id=schedule["id"])
    else:
        group = e2e_client.post("/v1/tags/groups", json={"name": "그룹", "color": "#FF5733"}).json()
        todo = e2e_client.post("/v1/todos", json={"title": "할 일", "tag_group_id": group["id"]}).json()
        timer_id, expires_at = _expired_timer(e2e_client, todo_id=todo["id"])
    after_commit_items.clear()

    if path == "todo_deadline":
        response = e2e_client.patch(f"/v1/todos/{todo['id']}", json={"deadline": "2024-01-20T10:00:00Z"})
    elif path == "todo_unlink":
        response = e2e_client.delete(f"/v1/todos/{todo['id']}", params={"linked_timer_policy": "unlink"})
    else:
        response = e2e_client.delete(f"/v1/schedules/{schedule['id']}", params={"linked_timer_policy": "unlink"})
    assert response.status_code == 200, response.text

    events = _timer_events(after_commit_items, timer_id)
    assert [e["action"] for e in events] == ["expire", "update"]
    for event in events:
        assert event["timer"]["status"] == "PAUSED"
        assert event["timer"]["elapsed_time"] == ALLOCATED
    stored = _stored(timer_id)
    assert stored.status == "PAUSED"
    assert [h["action"] for h in stored.pause_history] == ["start", "expire"]
    _assert_expired(e2e_client.get(f"/v1/timers/{timer_id}").json(), expires_at)
