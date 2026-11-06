"""
타이머 REST 명령 테스트

POST /v1/timers, PATCH /v1/timers/{id}/pause|resume, POST /v1/timers/{id}/stop,
PATCH·DELETE /v1/timers/{id}

- 상태 전이와 pause_history, timezone 변환
- 응답 전에 커밋하고(get_db_committing, scope="function") 커밋된 변경이 실시간 이벤트로 나간다
"""
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.v1.timers import router as timers_router
from app.db.session import get_db_committing
from app.main import app

KST = timedelta(hours=9)


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _create(client, **params) -> dict:
    response = client.post(
        "/v1/timers", json={"title": "REST 타이머", "allocated_duration": 1800}, params=params
    )
    assert response.status_code == 201, response.text
    return response.json()


def _command(client, timer_id: str, action: str, **params):
    method = client.post if action == "stop" else client.patch
    return method(f"/v1/timers/{timer_id}/{action}", params=params)


# ============================================================
# 상태 전이와 pause_history
# ============================================================

@pytest.mark.e2e
def test_create_starts_running_timer(e2e_client):
    timer = _create(e2e_client)

    assert timer["status"] == "RUNNING"
    assert timer["allocated_duration"] == 1800
    assert timer["elapsed_time"] == 0
    assert [h["action"] for h in timer["pause_history"]] == ["start"]


@pytest.mark.e2e
def test_create_with_schedule(e2e_client):
    schedule = e2e_client.post(
        "/v1/schedules",
        json={"title": "일정", "start_time": "2024-01-01T10:00:00Z", "end_time": "2024-01-01T12:00:00Z"},
    ).json()

    response = e2e_client.post(
        "/v1/timers",
        json={"schedule_id": schedule["id"], "allocated_duration": 600},
        params={"include_schedule": True},
    )

    assert response.status_code == 201
    assert response.json()["schedule"]["id"] == schedule["id"]


@pytest.mark.e2e
def test_full_lifecycle_records_pause_history(e2e_client):
    timer_id = _create(e2e_client)["id"]

    paused = _command(e2e_client, timer_id, "pause").json()
    assert paused["status"] == "PAUSED"
    assert paused["paused_at"] is not None

    resumed = _command(e2e_client, timer_id, "resume").json()
    assert resumed["status"] == "RUNNING"
    assert resumed["paused_at"] is None

    _command(e2e_client, timer_id, "pause")
    _command(e2e_client, timer_id, "resume")
    stopped = _command(e2e_client, timer_id, "stop").json()

    assert stopped["status"] == "COMPLETED"
    assert stopped["ended_at"] is not None
    history = stopped["pause_history"]
    assert [h["action"] for h in history] == ["start", "pause", "resume", "pause", "resume", "stop"]
    times = [_parse(h["at"]) for h in history]
    assert times == sorted(times)
    assert e2e_client.get(f"/v1/timers/{timer_id}").json()["pause_history"] == history


@pytest.mark.e2e
@pytest.mark.parametrize("setup, action", [
    ([], "resume"),
    (["pause"], "pause"),
    (["stop"], "stop"),
    (["stop"], "pause"),
])
def test_invalid_transition_is_400(e2e_client, after_commit_items, setup, action):
    timer_id = _create(e2e_client)["id"]
    for step in setup:
        assert _command(e2e_client, timer_id, step).status_code == 200
    after_commit_items.clear()

    response = _command(e2e_client, timer_id, action)

    assert response.status_code == 400
    assert after_commit_items == []


@pytest.mark.e2e
@pytest.mark.parametrize("action", ["pause", "resume", "stop"])
def test_unknown_timer_is_404(e2e_client, action):
    assert _command(e2e_client, str(uuid4()), action).status_code == 404


# ============================================================
# timezone
# ============================================================

@pytest.mark.e2e
@pytest.mark.parametrize("tz", ["Asia/Seoul", "+09:00"])
def test_timezone_applies_to_fields_and_pause_history(e2e_client, tz):
    timer = _create(e2e_client, timezone=tz)
    assert _parse(timer["started_at"]).utcoffset() == KST
    assert _parse(timer["pause_history"][0]["at"]).utcoffset() == KST

    paused = _command(e2e_client, timer["id"], "pause", timezone=tz).json()

    assert _parse(paused["paused_at"]).utcoffset() == KST
    assert [_parse(h["at"]).utcoffset() for h in paused["pause_history"]] == [KST, KST]


@pytest.mark.e2e
def test_utc_timezone_returns_utc(e2e_client):
    timer = _create(e2e_client, timezone="UTC")

    assert _parse(timer["started_at"]).utcoffset() == timedelta(0)


# ============================================================
# 실시간 이벤트
# ============================================================

@pytest.mark.e2e
def test_command_events_are_sent_after_commit(e2e_client, after_commit_items):
    timer = _create(e2e_client, timezone="Asia/Seoul")
    _command(e2e_client, timer["id"], "pause")
    _command(e2e_client, timer["id"], "resume")
    _command(e2e_client, timer["id"], "stop")
    e2e_client.patch(f"/v1/timers/{timer['id']}", json={"title": "바뀐 제목"})
    e2e_client.delete(f"/v1/timers/{timer['id']}")

    messages = [item["message"] for item in after_commit_items]
    assert [(m["type"], m["payload"]["action"]) for m in messages] == [
        ("timer.created", "start"),
        ("timer.updated", "pause"),
        ("timer.updated", "resume"),
        ("timer.updated", "stop"),
        ("timer.updated", "update"),
        ("timer.deleted", "delete"),
    ]
    assert len({m["id"] for m in messages}) == len(messages)
    assert all(m["from_user"] == "test-user-id" for m in messages)
    assert all(m["payload"]["actor_name"] == "Test User" for m in messages)
    assert all(item["users"] == {"test-user-id"} for item in after_commit_items)

    created = messages[0]["payload"]["timer"]
    assert created["id"] == timer["id"]
    # 요청의 timezone과 무관하게 이벤트는 UTC
    assert _parse(created["started_at"]).utcoffset() == timedelta(0)
    assert _parse(messages[0]["timestamp"]).utcoffset() == timedelta(0)
    assert messages[-1]["payload"]["timer"] is None
    assert messages[-1]["payload"]["timer_id"] == timer["id"]


@pytest.mark.e2e
def test_event_elapsed_matches_response(e2e_client, after_commit_items):
    timer_id = _create(e2e_client)["id"]
    after_commit_items.clear()

    paused = _command(e2e_client, timer_id, "pause").json()

    event_timer = after_commit_items[0]["message"]["payload"]["timer"]
    assert event_timer["elapsed_time"] == paused["elapsed_time"]
    assert event_timer["updated_at"] is not None


@pytest.mark.e2e
def test_friends_receive_events_by_visibility(multi_user_e2e, after_commit_items):
    owner = multi_user_e2e.as_user("owner")
    friend = multi_user_e2e.as_user("friend")
    stranger = multi_user_e2e.as_user("stranger")
    stranger.get("/v1/users/me")

    friend_code = friend.get("/v1/users/me").json()["friend_code"]
    assert owner.post("/v1/friends/requests", json={"friend_code": friend_code}).status_code == 201
    request_id = friend.get("/v1/friends/requests/received").json()[0]["id"]
    assert friend.post(f"/v1/friends/requests/{request_id}/accept").status_code == 200

    timer_id = _create(owner)["id"]
    assert after_commit_items[-1]["users"] == {"owner"}
    assert owner.put(f"/v1/visibility/timer/{timer_id}", json={"level": "public"}).status_code == 200
    after_commit_items.clear()

    assert _command(owner, timer_id, "pause").status_code == 200

    [item] = after_commit_items
    assert item["users"] == {"owner", "friend"}
    assert item["message"]["payload"]["actor_name"] == "User owner"


# ============================================================
# 응답 전 커밋
# ============================================================

COMMAND_ROUTES = {
    ("POST", "/timers"),
    ("PATCH", "/timers/{timer_id}/pause"),
    ("PATCH", "/timers/{timer_id}/resume"),
    ("POST", "/timers/{timer_id}/stop"),
    ("PATCH", "/timers/{timer_id}"),
    ("DELETE", "/timers/{timer_id}"),
}


def test_command_routes_commit_in_function_scope():
    found = set()
    for route in timers_router.routes:
        for method in route.methods:
            if (method, route.path) not in COMMAND_ROUTES:
                continue
            found.add((method, route.path))
            scopes = [d.scope for d in route.dependant.dependencies if d.call is get_db_committing]
            assert scopes == ["function"], (method, route.path)

    assert found == COMMAND_ROUTES


@pytest.mark.e2e
def test_event_is_handed_off_before_response_start(e2e_client, after_commit_items):
    events_at_response_start: list[int] = []

    async def recording_app(scope, receive, send):
        async def wrapped_send(message):
            if message["type"] == "http.response.start":
                events_at_response_start.append(len(after_commit_items))
            await send(message)

        await app(scope, receive, wrapped_send)

    response = TestClient(recording_app).post(
        "/v1/timers", json={"title": "순서", "allocated_duration": 60}
    )

    assert response.status_code == 201
    assert events_at_response_start == [1]
    assert UUID(after_commit_items[0]["message"]["id"])
