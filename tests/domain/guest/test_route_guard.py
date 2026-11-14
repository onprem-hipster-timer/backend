"""모든 경로가 게스트 토큰을 거부하는지 (허용 목록 밖)

새 경로가 게스트를 받으려면 아래 GUEST_TOKEN_NOT_REFUSED에 이유와 함께 올려야 한다.
"""
import re
import uuid

import pytest
from fastapi.routing import iter_route_contexts
from starlette.websockets import WebSocketDisconnect

from app.main import app
from tests.domain.guest.helpers import make_guest

# (메서드, 경로) — 게스트 토큰을 거부하지 않는 경로
GUEST_TOKEN_NOT_REFUSED = {
    # 게스트 경로
    ("POST", "/v1/guests/enter"),  # 인증 없음 (입장)
    ("DELETE", "/v1/guests/me"),  # 게스트 토큰 전용
    # 사용자 인증을 쓰지 않는 경로
    ("GET", "/health"),
    ("GET", "/openapi.json"),
    ("GET", "/docs"),
    ("GET", "/docs/oauth2-redirect"),
    ("GET", "/redoc"),
    ("GET", "/v1/holidays"),
    ("GET", "/ws-playground"),
    ("GET", "/auth/.well-known/jwks.json"),
    ("GET", "/auth//.well-known/jwks.json"),
    ("GET", "/auth/.well-known/openid-configuration"),
    ("GET", "/auth//.well-known/openid-configuration"),
    ("POST", "/internal/accounts/purge"),  # 공유 토큰
    # Kratos 공개 API 프록시 (게스트도 세션 토큰으로 JWT를 받는다)
    *{(m, "/auth/{path:path}") for m in ("GET", "POST", "PUT", "PATCH", "DELETE")},
}

# WebSocket 경로 중 게스트 토큰을 거부하지 않는 경로
WEBSOCKET_NOT_REFUSED = {
    "/v1/graphql",  # GraphQL subscription 없음. 연결해도 쿼리를 실행할 수 없다
}


def _http_routes() -> list[tuple[str, str]]:
    routes = []
    for context in iter_route_contexts(app.routes):
        for method in sorted(context.methods or ()):
            if method != "HEAD":
                routes.append((method, context.path))
    return routes


def _websocket_paths() -> list[str]:
    paths = []
    for context in iter_route_contexts(app.routes):
        if context.methods:
            continue
        # 포함된 라우터의 WebSocket 경로는 접두사가 붙은 starlette 경로에만 있다 (FastAPI 0.142)
        effective = context._route_context
        if effective is not None and effective.starlette_route is not None:
            paths.append(effective.starlette_route.path)
        else:
            paths.append(context.original_route.path)
    return paths


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path)


def test_allow_list_has_no_stale_entries():
    assert GUEST_TOKEN_NOT_REFUSED <= set(_http_routes())
    assert WEBSOCKET_NOT_REFUSED <= set(_websocket_paths())


def test_every_http_route_refuses_guest_token(guest_client, kratos, host, tokens):
    guest = make_guest(kratos, uuid.uuid4())
    headers = tokens.guest(guest.identity_id)

    not_refused = []
    for method, path in _http_routes():
        if (method, path) in GUEST_TOKEN_NOT_REFUSED:
            continue
        r = guest_client.request(method, _concrete(path), headers=headers)
        if r.status_code != 403:
            not_refused.append((method, path, r.status_code))

    assert not_refused == []


def test_every_websocket_route_refuses_guest_token(guest_client, kratos, tokens):
    guest = make_guest(kratos, uuid.uuid4())
    token = tokens.make(guest.identity_id, "guest")

    paths = [p for p in _websocket_paths() if p not in WEBSOCKET_NOT_REFUSED]
    assert paths
    for path in paths:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with guest_client.websocket_connect(_concrete(path), subprotocols=[f"authorization.bearer.{token}"]) as ws:
                ws.receive_json()
        assert exc_info.value.code == 1008, path
