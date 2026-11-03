"""
/auth/* → Kratos 공개 API 프록시 테스트

실제 Kratos 대신 httpx.MockTransport가 upstream 역할을 하고, 받은 요청을 기록한다.
"""
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import auth_proxy
from app.core import courier
from app.core.config import Settings

UPSTREAM = "http://kratos.test"


class Upstream:
    """받은 요청을 기록하고 handler가 정한 응답을 돌려주는 가짜 Kratos"""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.handler = lambda request: httpx.Response(200, json={"ok": True})

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)


@pytest.fixture
def upstream(monkeypatch):
    upstream = Upstream()
    monkeypatch.setattr(auth_proxy, "settings", Settings(KRATOS_PUBLIC_URL=UPSTREAM))
    monkeypatch.setattr(
        auth_proxy,
        "_make_client",
        lambda: httpx.AsyncClient(base_url=UPSTREAM, transport=httpx.MockTransport(upstream)),
    )
    return upstream


@pytest.fixture
def client(upstream):
    app = FastAPI()
    app.include_router(auth_proxy.router)
    return TestClient(app)


def test_strips_auth_prefix_and_keeps_query(client, upstream):
    response = client.get("/auth/sessions/whoami?tokenize_as=api")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    sent = upstream.requests[0]
    assert sent.method == "GET"
    assert sent.url.path == "/sessions/whoami"
    assert sent.url.query == b"tokenize_as=api"


def test_forwards_only_allowlisted_headers(client, upstream):
    client.get(
        "/auth/sessions/whoami",
        headers={
            "X-Session-Token": "ory_st_abc",
            "Authorization": "Bearer ory_st_abc",
            "Accept": "application/json",
            "X-Forwarded-Host": "api.example.com",
            "X-Forwarded-Proto": "https",
            "Cf-Connecting-IP": "203.0.113.7",
            "Cookie": "ory_kratos_session=s1",
            "X-Origin-Verify": "secret",
        },
    )

    sent = upstream.requests[0].headers
    assert sent["x-session-token"] == "ory_st_abc"
    assert sent["authorization"] == "Bearer ory_st_abc"
    assert sent["accept"] == "application/json"
    assert sent["x-forwarded-host"] == "api.example.com"
    assert sent["x-forwarded-proto"] == "https"
    assert sent["cf-connecting-ip"] == "203.0.113.7"
    assert sent["cookie"] == "ory_kratos_session=s1"
    assert "x-origin-verify" not in sent
    assert sent["host"] == "kratos.test"


def test_forwards_method_and_body(client, upstream):
    """API 플로우 로그아웃은 본문이 있는 DELETE다"""
    response = client.request(
        "DELETE", "/auth/self-service/logout/api", json={"session_token": "ory_st_abc"}
    )

    assert response.status_code == 200
    sent = upstream.requests[0]
    assert sent.method == "DELETE"
    assert sent.url.path == "/self-service/logout/api"
    assert sent.headers["content-type"] == "application/json"
    assert sent.content == b'{"session_token":"ory_st_abc"}'


def test_keeps_each_set_cookie(client, upstream):
    upstream.handler = lambda request: httpx.Response(
        200,
        headers=[("set-cookie", "a=1; Path=/; HttpOnly"), ("set-cookie", "b=2; Path=/")],
        json={},
    )

    response = client.get("/auth/self-service/login/browser")

    assert response.headers.get_list("set-cookie") == ["a=1; Path=/; HttpOnly", "b=2; Path=/"]


def test_drops_upstream_date_and_server_headers(client, upstream):
    """uvicorn이 붙이는 date·server와 겹치지 않게 upstream 것은 버린다"""
    upstream.handler = lambda request: httpx.Response(
        200, headers={"date": "Tue, 03 Nov 2026 00:00:00 GMT", "server": "kratos"}, json={}
    )

    response = client.get("/auth/sessions/whoami")

    # 서버(uvicorn)가 자기 것을 붙이므로 프록시는 upstream 것을 넘기지 않는다
    assert response.headers.get_list("date") == []
    assert "server" not in response.headers


def test_passes_redirect_through(client, upstream):
    upstream.handler = lambda request: httpx.Response(
        303, headers={"location": "https://app.example.com/login?flow=f1"}
    )

    response = client.get("/auth/self-service/login/browser", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "https://app.example.com/login?flow=f1"


def test_upstream_unreachable_returns_502(client, upstream):
    def refuse(request):
        raise httpx.ConnectError("connection refused", request=request)

    upstream.handler = refuse

    response = client.get("/auth/sessions/whoami")

    assert response.status_code == 502
    assert response.json() == {"detail": "Authentication service unavailable"}


@pytest.mark.parametrize(
    ("method", "path", "status", "triggered"),
    [
        ("POST", "/auth/self-service/registration?flow=f", 200, True),
        ("POST", "/auth/self-service/verification?flow=f", 200, True),
        ("POST", "/auth/self-service/recovery?flow=f", 200, True),
        ("POST", "/auth/self-service/settings?flow=f", 200, True),
        ("POST", "/auth/self-service/registration?flow=f", 303, True),
        ("POST", "/auth/self-service/registration?flow=f", 400, False),
        ("POST", "/auth/self-service/login?flow=f", 200, False),
        ("GET", "/auth/self-service/registration/api", 200, False),
    ],
)
def test_triggers_courier_only_after_mail_flow_submit(client, upstream, monkeypatch, method, path, status, triggered):
    calls = []
    monkeypatch.setattr(courier, "trigger", lambda: calls.append(True))
    upstream.handler = lambda request: httpx.Response(status, json={})

    client.request(method, path, json={} if method == "POST" else None, follow_redirects=False)

    assert bool(calls) is triggered


def test_not_configured_returns_404(client, upstream, monkeypatch):
    monkeypatch.setattr(auth_proxy, "settings", Settings(KRATOS_PUBLIC_URL=""))

    response = client.get("/auth/sessions/whoami")

    assert response.status_code == 404
    assert upstream.requests == []


# ============================================================================
# 실제 앱의 미들웨어 스택(CORS, Auth, RateLimit, RequestLogger)을 거쳐도 유지되는지
# ============================================================================

@pytest.fixture
def app_client(upstream):
    from app.main import app

    return TestClient(app)


def test_full_app_keeps_each_set_cookie(app_client, upstream):
    upstream.handler = lambda request: httpx.Response(
        200, headers=[("set-cookie", "a=1; Path=/"), ("set-cookie", "b=2; Path=/")], json={}
    )

    response = app_client.get("/auth/self-service/login/browser")

    assert response.headers.get_list("set-cookie") == ["a=1; Path=/", "b=2; Path=/"]


def test_full_app_answers_cors_preflight_for_auth(app_client, upstream):
    response = app_client.options(
        "/auth/self-service/login",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-session-token",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "x-session-token" in response.headers["access-control-allow-headers"].lower()
    assert upstream.requests == []
