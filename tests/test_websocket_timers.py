"""
타이머 WebSocket 테스트 (/v1/ws/timers, 수신 전용)

- 연결 직후 connected, `ping` → `pong`, 그 외 메시지는 무시
- 인증에 실패하면 핸드셰이크를 마친 뒤 1008로 닫는다
- REST 명령이 커밋되면 받는 사람(소유자, 공개 범위상 친구)의 소켓으로 이벤트가 온다 (InProcessPublisher)
"""
import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta
from uuid import UUID

import pytest
from starlette.websockets import WebSocketDisconnect

from app.realtime.publisher import InProcessPublisher, as_after_commit_sink
from app.shared.uow import set_after_commit_sink
from app.websocket.manager import connection_manager


@contextmanager
def inprocess_delivery(ws):
    """ws를 처리하는 이벤트 루프로 보내는 InProcessPublisher를 커밋 후 큐의 sink로 건다"""
    loop = ws.portal.call(asyncio.get_running_loop)
    previous = set_after_commit_sink(as_after_commit_sink(InProcessPublisher(loop)))
    try:
        yield
    finally:
        set_after_commit_sink(previous)


def _create_timer(client) -> str:
    response = client.post("/v1/timers", json={"title": "소켓", "allocated_duration": 600})
    assert response.status_code == 201
    return response.json()["id"]


def test_connect_sends_connected(e2e_client):
    with e2e_client.websocket_connect("/v1/ws/timers") as ws:
        message = ws.receive_json()

    assert message["type"] == "connected"
    assert UUID(message["id"])
    assert message["from_user"] is None
    assert message["payload"] == {}
    timestamp = datetime.fromisoformat(message["timestamp"].replace("Z", "+00:00"))
    assert timestamp.utcoffset() == timedelta(0)


def test_echoes_bearer_subprotocol(e2e_client):
    protocol = "authorization.bearer.token"

    with e2e_client.websocket_connect("/v1/ws/timers", subprotocols=[protocol]) as ws:
        assert ws.accepted_subprotocol == protocol
        assert ws.receive_json()["type"] == "connected"


@pytest.fixture
def oidc_rejects_tokens(monkeypatch):
    """소켓 인증을 켜고 토큰 검증은 항상 실패시킨다"""
    async def reject(token):
        raise ValueError("invalid token")

    monkeypatch.setattr("app.websocket.auth.settings.OIDC_ENABLED", True)
    monkeypatch.setattr("app.websocket.auth.oidc_client.verify_token", reject)


@pytest.mark.parametrize(
    ("subprotocols", "reason"),
    [
        ([], "Authentication required"),
        (["authorization.bearer.invalid"], "Token verification failed"),
    ],
)
def test_auth_failure_closes_with_1008_after_handshake(e2e_client, oidc_rejects_tokens, subprotocols, reason):
    # 핸드셰이크 전에 닫으면 HTTP 403이 되어 브라우저에는 1008이 아닌 1006으로 보인다
    with e2e_client.websocket_connect("/v1/ws/timers", subprotocols=subprotocols) as ws:
        assert ws.accepted_subprotocol == (subprotocols[0] if subprotocols else None)
        with pytest.raises(WebSocketDisconnect) as exc_info:
            ws.receive_json()

    assert exc_info.value.code == 1008
    assert exc_info.value.reason.startswith(reason)


def test_auth_failure_echoes_bearer_among_several_subprotocols(e2e_client, oidc_rejects_tokens):
    with e2e_client.websocket_connect(
        "/v1/ws/timers", subprotocols=["graphql-ws", "authorization.bearer.invalid"]
    ) as ws:
        assert ws.accepted_subprotocol == "authorization.bearer.invalid"
        with pytest.raises(WebSocketDisconnect) as exc_info:
            ws.receive_json()

    assert exc_info.value.code == 1008


def test_ping_pong(e2e_client):
    with e2e_client.websocket_connect("/v1/ws/timers") as ws:
        ws.receive_json()
        ws.send_text("ping")

        assert ws.receive_text() == "pong"


def test_other_messages_are_ignored(e2e_client):
    with e2e_client.websocket_connect("/v1/ws/timers") as ws:
        ws.receive_json()
        ws.send_json({"type": "timer.create", "payload": {"allocated_duration": 1800}})
        ws.send_text("not json")
        ws.send_bytes(b"ping")
        ws.send_text("ping")

        assert ws.receive_text() == "pong"

    assert e2e_client.get("/v1/timers").json() == []


def test_disconnect_removes_connection(e2e_client):
    with e2e_client.websocket_connect("/v1/ws/timers") as ws:
        ws.receive_json()
        assert connection_manager.is_user_online("test-user-id")

    assert not connection_manager.is_user_online("test-user-id")


def test_rest_commands_reach_own_socket(e2e_client):
    with e2e_client.websocket_connect("/v1/ws/timers") as ws, inprocess_delivery(ws):
        ws.receive_json()

        timer_id = _create_timer(e2e_client)
        created = ws.receive_json()
        assert e2e_client.patch(f"/v1/timers/{timer_id}/pause").status_code == 200
        paused = ws.receive_json()

    assert created["type"] == "timer.created"
    assert created["payload"]["timer"]["id"] == timer_id
    assert (paused["type"], paused["payload"]["action"]) == ("timer.updated", "pause")
    assert paused["payload"]["timer"]["status"] == "PAUSED"


def test_friend_socket_receives_event_by_visibility(multi_user_e2e):
    owner = multi_user_e2e.as_user("owner")
    friend = multi_user_e2e.as_user("friend")
    friend_code = friend.get("/v1/users/me").json()["friend_code"]
    assert owner.post("/v1/friends/requests", json={"friend_code": friend_code}).status_code == 201
    request_id = friend.get("/v1/friends/requests/received").json()[0]["id"]
    assert friend.post(f"/v1/friends/requests/{request_id}/accept").status_code == 200
    timer_id = _create_timer(owner)
    assert owner.put(f"/v1/visibility/timer/{timer_id}", json={"level": "friends"}).status_code == 200

    # 소켓의 사용자는 연결할 때 정해진다
    friend._set_user_override()
    with friend._client.websocket_connect("/v1/ws/timers") as ws, inprocess_delivery(ws):
        ws.receive_json()
        assert owner.patch(f"/v1/timers/{timer_id}/pause").status_code == 200
        event = ws.receive_json()

    assert event["type"] == "timer.updated"
    assert event["from_user"] == "owner"
    assert event["payload"]["actor_name"] == "User owner"
    assert event["payload"]["timer"]["id"] == timer_id
