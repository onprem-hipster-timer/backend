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
    assert "cookie" not in sent  # 인증은 쿠키가 아니라 세션 토큰과 JWT
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


def test_drops_set_cookie(client, upstream):
    upstream.handler = lambda request: httpx.Response(
        200,
        headers=[("set-cookie", "a=1; Path=/; HttpOnly"), ("set-cookie", "b=2; Path=/")],
        json={},
    )

    response = client.get("/auth/self-service/login/api")

    assert response.status_code == 200
    assert "set-cookie" not in response.headers


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


# ============================================================================
# 설정 제출: 새어 나간 비밀번호만으로 계정을 차지하지 못하게 한다
# (응답 모양은 로컬 Kratos v26.2.0 실측값)
# ============================================================================

RECOVERY_SESSION = {"authentication_methods": [{"method": "code_recovery"}]}
PASSWORD_SESSION = {"authentication_methods": [{"method": "password"}]}
REFRESHED_RECOVERY_SESSION = {
    "authentication_methods": [{"method": "code_recovery"}, {"method": "password"}]
}
SETTINGS_SUBMIT = "/auth/self-service/settings?flow=f1"


def kratos_with_session(upstream, session, whoami_status=200):
    """whoami는 session으로, 설정 제출은 성공으로 답하는 가짜 Kratos"""

    def handler(request):
        if request.url.path == "/sessions/whoami":
            return httpx.Response(whoami_status, json=session)
        return httpx.Response(200, json={"state": "success"})

    upstream.handler = handler


def settings_forwarded(upstream):
    return [r for r in upstream.requests if r.url.path == "/self-service/settings"]


def test_settings_password_with_email_recovery_session_is_forwarded(client, upstream):
    kratos_with_session(upstream, RECOVERY_SESSION)

    response = client.post(
        SETTINGS_SUBMIT,
        json={"method": "password", "password": "New-Pass-123"},
        headers={"X-Session-Token": "ory_st_recovery"},
    )

    assert response.status_code == 200
    whoami = upstream.requests[0]
    assert whoami.url.path == "/sessions/whoami"
    assert whoami.headers["x-session-token"] == "ory_st_recovery"
    assert len(settings_forwarded(upstream)) == 1


def test_settings_password_form_body_with_recovery_session_is_forwarded(client, upstream):
    kratos_with_session(upstream, RECOVERY_SESSION)

    response = client.post(
        SETTINGS_SUBMIT,
        content=b"method=password&password=New-Pass-123",
        headers={
            "X-Session-Token": "ory_st_recovery",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )

    assert response.status_code == 200
    assert len(settings_forwarded(upstream)) == 1


@pytest.mark.parametrize(
    "session",
    [PASSWORD_SESSION, REFRESHED_RECOVERY_SESSION],
    ids=["password_login", "recovery_then_password_refresh"],
)
def test_settings_password_without_email_recovery_is_rejected(client, upstream, session):
    """비밀번호만 아는 사람(비밀번호 로그인·재인증 세션)은 비밀번호를 바꿀 수 없다"""
    kratos_with_session(upstream, session)

    response = client.post(
        SETTINGS_SUBMIT,
        json={"method": "password", "password": "Attacker-Pass-999"},
        headers={"X-Session-Token": "ory_st_attacker"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["id"] == "settings_require_email_recovery"
    assert settings_forwarded(upstream) == []


@pytest.mark.parametrize(
    "body",
    [
        {"method": "profile", "traits": {"email": "attacker@example.com"}},
        {"method": "oidc", "link": "google"},
        {"method": "oidc", "unlink": "google"},
        {"method": "totp", "totp_code": "123456"},
        {"password": "no-method"},
    ],
    ids=["email_change", "oidc_link", "oidc_unlink", "other_method", "no_method"],
)
def test_settings_other_than_password_are_rejected_even_after_recovery(client, upstream, body):
    """이메일 변경·소셜 계정 연결은 앱이 쓰지 않는다. 복구 세션이어도 막는다"""
    kratos_with_session(upstream, RECOVERY_SESSION)

    response = client.post(SETTINGS_SUBMIT, json=body, headers={"X-Session-Token": "ory_st_recovery"})

    assert response.status_code == 403
    assert settings_forwarded(upstream) == []


def test_settings_without_session_token_is_rejected(client, upstream):
    kratos_with_session(upstream, RECOVERY_SESSION)

    response = client.post(SETTINGS_SUBMIT, json={"method": "password", "password": "x"})

    assert response.status_code == 403
    assert upstream.requests == []


def test_settings_with_ended_session_is_rejected(client, upstream):
    kratos_with_session(upstream, {"error": {"id": "session_inactive"}}, whoami_status=401)

    response = client.post(
        SETTINGS_SUBMIT,
        json={"method": "password", "password": "x"},
        headers={"X-Session-Token": "ory_st_ended"},
    )

    assert response.status_code == 403
    assert settings_forwarded(upstream) == []


def test_settings_with_unreadable_body_is_rejected(client, upstream):
    kratos_with_session(upstream, RECOVERY_SESSION)

    response = client.post(
        SETTINGS_SUBMIT,
        content=b"{not json",
        headers={"X-Session-Token": "ory_st_recovery", "Content-Type": "application/json"},
    )

    assert response.status_code == 403
    assert settings_forwarded(upstream) == []


def test_settings_flow_creation_is_not_blocked(client, upstream):
    """설정 플로우를 만드는 GET은 막지 않는다 (제출만 검사)"""
    response = client.get("/auth/self-service/settings/api", headers={"X-Session-Token": "t"})

    assert response.status_code == 200
    assert upstream.requests[0].url.path == "/self-service/settings/api"


def test_allowed_settings_submit_still_triggers_courier(client, upstream, monkeypatch):
    calls = []
    monkeypatch.setattr(courier, "trigger", lambda: calls.append(True))
    kratos_with_session(upstream, RECOVERY_SESSION)

    client.post(
        SETTINGS_SUBMIT,
        json={"method": "password", "password": "New-Pass-123"},
        headers={"X-Session-Token": "ory_st_recovery"},
    )

    assert calls == [True]


@pytest.mark.parametrize(
    "path",
    [
        "/auth/self-service/settings/?flow=f1",
        "/auth/self-service/Settings?flow=f1",
        "/auth/self-service/x/../settings?flow=f1",
        "/auth/self-service/%73ettings?flow=f1",
    ],
)
def test_settings_path_variants_are_also_guarded(client, upstream, path):
    """경로를 바꿔 써도 Kratos로 나갈 경로 기준으로 검사한다"""
    kratos_with_session(upstream, PASSWORD_SESSION)

    response = client.post(
        path,
        json={"method": "password", "password": "Attacker-Pass-999"},
        headers={"X-Session-Token": "ory_st_attacker"},
    )

    assert response.status_code == 403
    assert [r for r in upstream.requests if r.method == "POST"] == []


def test_settings_body_with_duplicate_keys_is_rejected(client, upstream):
    """키가 겹치면 프록시와 Kratos가 서로 다른 method를 읽을 수 있다"""
    kratos_with_session(upstream, RECOVERY_SESSION)

    response = client.post(
        SETTINGS_SUBMIT,
        content=b'{"method": "password", "method": "profile", "traits": {"email": "a@example.com"}}',
        headers={"X-Session-Token": "ory_st_recovery", "Content-Type": "application/json"},
    )

    assert response.status_code == 403
    assert settings_forwarded(upstream) == []


def test_allowed_settings_submit_drops_other_session_header(client, upstream):
    """검사한 X-Session-Token 세션으로만 처리되게 Authorization은 넘기지 않는다"""
    kratos_with_session(upstream, RECOVERY_SESSION)

    client.post(
        SETTINGS_SUBMIT,
        json={"method": "password", "password": "New-Pass-123"},
        headers={"X-Session-Token": "ory_st_recovery", "Authorization": "Bearer ory_st_other"},
    )

    sent = settings_forwarded(upstream)[0]
    assert sent.headers["x-session-token"] == "ory_st_recovery"
    assert "authorization" not in sent.headers
