"""
/auth/* → Kratos 공개 API 프록시 테스트

실제 Kratos 대신 httpx.MockTransport가 upstream 역할을 하고, 받은 요청을 기록한다.
"""
import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.core.config as app_config
from app.api import auth_proxy
from app.core import courier, turnstile
from app.core.config import Settings
from app.middleware.guest_gate import GuestGateMiddleware
from app.ratelimit.config import AUTH_SUBMIT_PER_IP

UPSTREAM = "http://kratos.test"


async def _record(calls: list) -> None:
    calls.append(True)


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
    # 요청 한도는 tests/domain/guest/test_rate_limits.py가 본다
    monkeypatch.setattr(app_config.settings, "RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(
        auth_proxy,
        "_make_client",
        lambda: httpx.AsyncClient(base_url=UPSTREAM, transport=httpx.MockTransport(upstream)),
    )
    return upstream


@pytest.fixture
def client(upstream):
    app = FastAPI()
    app.add_middleware(GuestGateMiddleware)  # 제출은 인터셉터가 읽어 프록시에 넘긴다
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
    monkeypatch.setattr(courier, "start", lambda: _record(calls))
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


def kratos_with_session(upstream, session, whoami_status=200, base_path=""):
    """whoami는 session으로, 설정 제출은 성공으로 답하는 가짜 Kratos (base_path: KRATOS_PUBLIC_URL의 경로)"""

    def handler(request):
        if request.url.path == f"{base_path}/sessions/whoami":
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


GUEST_SESSION = {
    "authentication_methods": [{"method": "password"}],
    "identity": {"id": "guest-identity", "schema_id": "guest", "traits": {"handle": "h", "name": "민수"}},
}
MEMBER_SESSION = {
    "authentication_methods": [{"method": "password"}],
    "identity": {"schema_id": "default", "traits": {"email": "m@example.com"}},
}
GUEST_RENAME = {"method": "profile", "traits": {"handle": "h", "name": "철수"}}


@pytest.fixture
def guest_enabled(monkeypatch):
    monkeypatch.setattr(auth_proxy, "settings", Settings(KRATOS_PUBLIC_URL=UPSTREAM, GUEST_ENABLED=True,
                                                         KRATOS_ADMIN_URL="http://admin.test",
                                                         KRATOS_HOOK_API_KEY="k", TURNSTILE_SECRET_KEY="s"))


def test_settings_profile_of_guest_session_without_identity_id_is_rejected(client, upstream, guest_enabled):
    """게스트 이름 변경은 tests/domain/guest/test_rename_proxy.py에서 DB와 함께 확인한다"""
    kratos_with_session(upstream, {**GUEST_SESSION, "identity": {"schema_id": "guest", "traits": {"handle": "h"}}})

    response = client.post(SETTINGS_SUBMIT, json=GUEST_RENAME, headers={"X-Session-Token": "ory_st_guest"})

    assert response.status_code == 403
    assert settings_forwarded(upstream) == []


def test_settings_profile_of_member_session_is_rejected_when_guest_enabled(client, upstream, guest_enabled):
    kratos_with_session(upstream, MEMBER_SESSION)

    response = client.post(
        SETTINGS_SUBMIT,
        json={"method": "profile", "traits": {"email": "other@example.com"}},
        headers={"X-Session-Token": "ory_st_member"},
    )

    assert response.status_code == 403
    assert settings_forwarded(upstream) == []


def test_settings_profile_of_guest_session_is_rejected_when_guest_disabled(client, upstream):
    kratos_with_session(upstream, GUEST_SESSION)

    response = client.post(SETTINGS_SUBMIT, json=GUEST_RENAME, headers={"X-Session-Token": "ory_st_guest"})

    assert response.status_code == 403
    assert settings_forwarded(upstream) == []


def test_settings_profile_with_ended_session_is_rejected_when_guest_enabled(client, upstream, guest_enabled):
    kratos_with_session(upstream, GUEST_SESSION, whoami_status=401)

    response = client.post(SETTINGS_SUBMIT, json=GUEST_RENAME, headers={"X-Session-Token": "ory_st_guest"})

    assert response.status_code == 403
    assert settings_forwarded(upstream) == []


@pytest.mark.parametrize(
    "body",
    [{"method": "password", "password": "New-Pass-123"}, {"method": "oidc", "link": "google"}],
    ids=["password", "oidc_link"],
)
def test_guest_session_other_settings_are_rejected(client, upstream, guest_enabled, body):
    kratos_with_session(upstream, GUEST_SESSION)

    response = client.post(SETTINGS_SUBMIT, json=body, headers={"X-Session-Token": "ory_st_guest"})

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

    assert response.status_code == 400
    assert response.json()["error"]["id"] == "invalid_request_body"
    assert upstream.requests == []


def test_settings_flow_creation_is_not_blocked(client, upstream):
    """설정 플로우를 만드는 GET은 막지 않는다 (제출만 검사)"""
    response = client.get("/auth/self-service/settings/api", headers={"X-Session-Token": "t"})

    assert response.status_code == 200
    assert upstream.requests[0].url.path == "/self-service/settings/api"


def test_allowed_settings_submit_still_triggers_courier(client, upstream, monkeypatch):
    calls = []
    monkeypatch.setattr(courier, "start", lambda: _record(calls))
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

    assert response.status_code == 400
    assert response.json()["error"]["id"] == "invalid_request_body"
    assert upstream.requests == []


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


def test_settings_body_with_keys_differing_only_in_case_is_rejected(client, upstream):
    """키는 대소문자 구분 없이 비교해 Method와 method를 겹친 키로 본다"""
    kratos_with_session(upstream, RECOVERY_SESSION)

    response = client.post(
        SETTINGS_SUBMIT,
        content=b'{"method": "password", "Method": "profile"}',
        headers={"X-Session-Token": "ory_st_recovery", "Content-Type": "application/json"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["id"] == "invalid_request_body"
    assert upstream.requests == []


# --- 소셜 로그인 제출의 traits.email 제거 ---


def forwarded_json(upstream):
    return json.loads(upstream.requests[-1].content)


@pytest.mark.parametrize("flow", ["registration", "login"])
def test_oidc_submit_drops_client_email(client, upstream, flow):
    """처음 쓰는 소셜 계정이면 로그인 제출도 가입이 되므로 둘 다 지운다"""
    client.post(
        f"/auth/self-service/{flow}?flow=f1",
        json={"method": "oidc", "provider": "google", "traits": {"email": "other@example.com", "name": "A"}},
    )

    assert forwarded_json(upstream) == {"method": "oidc", "provider": "google", "traits": {"name": "A"}}


def test_oidc_submit_drops_email_under_differently_cased_keys(client, upstream):
    client.post(
        "/auth/self-service/registration?flow=f1",
        json={"Method": "oidc", "provider": "google", "Traits": {"Email": "other@example.com"}},
    )

    assert forwarded_json(upstream) == {"Method": "oidc", "provider": "google", "Traits": {}}


def test_oidc_form_submit_drops_client_email(client, upstream):
    client.post(
        "/auth/self-service/registration?flow=f1",
        content=b"method=oidc&provider=google&traits.email=other%40example.com&traits.name=A",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert upstream.requests[-1].content == b"method=oidc&provider=google&traits.name=A"


@pytest.mark.parametrize("path", ["/auth/self-service/registration/", "/auth/self-service/Registration"])
def test_oidc_submit_path_variants_are_also_cleaned(client, upstream, path):
    client.post(f"{path}?flow=f1", json={"method": "oidc", "provider": "google", "traits": {"email": "v@example.com"}})

    assert forwarded_json(upstream) == {"method": "oidc", "provider": "google", "traits": {}}


def test_password_registration_keeps_email(client, upstream):
    body = b'{"method": "password", "password": "Pass-123456", "traits": {"email": "me@example.com"}}'

    client.post(
        "/auth/self-service/registration?flow=f1",
        content=body,
        headers={"Content-Type": "application/json"},
    )

    assert upstream.requests[-1].content == body


@pytest.mark.parametrize(
    "content, content_type",
    [
        (b'{"method": "password", "method": "oidc", "traits": {"email": "v@example.com"}}', "application/json"),
        (b'{"method": "password", "Method": "oidc", "traits": {"email": "v@example.com"}}', "application/json"),
        (b"method=password&method=oidc&traits.email=v%40example.com", "application/x-www-form-urlencoded"),
        (b"not json", "application/json"),
    ],
)
def test_ambiguous_or_unreadable_registration_body_is_rejected(client, upstream, content, content_type):
    response = client.post(
        "/auth/self-service/registration?flow=f1",
        content=content,
        headers={"Content-Type": content_type},
    )

    assert response.status_code == 400
    assert upstream.requests == []


# ── 계정 접근 기록 (app/core/audit.py) ─────────────────────────────────────────

@pytest.fixture
def access_log(monkeypatch):
    import logging

    from app.core.audit import AUDIT_LOGGER_NAME

    lines: list[dict] = []

    class Capture(logging.Handler):
        def emit(self, record):
            lines.append(json.loads(record.getMessage()))

    handler = Capture()
    logger = logging.getLogger(AUDIT_LOGGER_NAME)
    monkeypatch.setattr(logger, "disabled", False)
    logger.addHandler(handler)
    yield lines
    logger.removeHandler(handler)


LOGIN_BODY = {
    "session_token": "ory_st_secret",
    "session": {"id": "s1", "identity": {"id": "identity-1", "traits": {"email": "me@example.com"}}},
}
REGISTRATION_BODY = {
    "identity": {"id": "identity-2", "traits": {"email": "new@example.com"}},
    "session_token": "ory_st_secret",
    "session": {"id": "s2", "identity": {"id": "identity-2", "traits": {"email": "new@example.com"}}},
}


@pytest.mark.parametrize(
    "path, body, event, identity_id",
    [
        ("/auth/self-service/login?flow=f1", LOGIN_BODY, "login", "identity-1"),
        ("/auth/self-service/registration?flow=f1", REGISTRATION_BODY, "registration", "identity-2"),
        ("/auth/self-service/registration?flow=f1", {"identity": {"id": "identity-3"}}, "registration", "identity-3"),
        ("/auth/self-service/login/?flow=f1", LOGIN_BODY, "login", "identity-1"),
    ],
)
def test_successful_login_and_registration_are_logged(client, upstream, access_log, path, body, event, identity_id):
    upstream.handler = lambda request: httpx.Response(200, json=body)

    response = client.post(path, json={"method": "password"})

    assert response.status_code == 200
    assert response.json() == body
    assert len(access_log) == 1
    line = access_log[0]
    assert list(line) == ["audit", "event", "identity_id", "ip", "at"]
    assert line["audit"] == "account_access"
    assert line["event"] == event
    assert line["identity_id"] == identity_id
    assert line["ip"] == "testclient"
    assert "example.com" not in json.dumps(line)
    assert "ory_st_secret" not in json.dumps(line)


@pytest.mark.parametrize(
    "method, path, status, body",
    [
        ("POST", "/auth/self-service/login?flow=f1", 400, {"ui": {"messages": []}}),
        ("POST", "/auth/self-service/login?flow=f1", 422, {"redirect_browser_to": "https://idp"}),
        ("GET", "/auth/self-service/login/api", 200, {"id": "flow-1", "ui": {}}),
        ("POST", "/auth/self-service/recovery?flow=f1", 200, {"identity": {"id": "identity-1"}}),
        ("POST", "/auth/self-service/verification?flow=f1", 200, {"session": {"identity": {"id": "identity-1"}}}),
        ("POST", "/auth/self-service/login?flow=f1", 200, {"session": {"identity": {}}}),
        ("POST", "/auth/self-service/login?flow=f1", 200, ["not", "an", "object"]),
    ],
)
def test_other_responses_are_not_logged(client, upstream, access_log, method, path, status, body):
    upstream.handler = lambda request: httpx.Response(status, json=body)

    response = client.request(method, path, json={"method": "password"} if method == "POST" else None)

    assert response.status_code == status
    assert access_log == []


def test_unreadable_login_response_is_passed_through_without_log(client, upstream, access_log):
    upstream.handler = lambda request: httpx.Response(200, content=b"not json")

    response = client.post("/auth/self-service/login?flow=f1", json={"method": "password"})

    assert response.status_code == 200
    assert response.content == b"not json"
    assert access_log == []


# ============ 게스트 handle 도메인 주소의 인증·복구 제출 ============

ADDRESS_FLOWS = ["/auth/self-service/verification?flow=f1", "/auth/self-service/recovery?flow=f1"]


def _forwarded(upstream, path):
    return [r for r in upstream.requests if r.url.path == path.split("?")[0].removeprefix("/auth")]


@pytest.mark.parametrize("path", ADDRESS_FLOWS)
@pytest.mark.parametrize(
    "email",
    [
        "x@guest.invalid",
        "x@GUEST.Invalid",
        "  x@guest.invalid  ",
        "X@Guest.INVALID\n",
        "\tx@guest.invalid\r\n",
        "\v\fX@GUEST.INVALID \r",
    ],
)
def test_address_flow_to_guest_domain_is_refused_json(client, upstream, monkeypatch, path, email):
    calls = []
    monkeypatch.setattr(courier, "start", lambda: _record(calls))

    response = client.post(path, json={"method": "code", "email": email})

    assert response.status_code == 400
    assert response.json()["error"]["id"] == "address_not_accepted"
    assert _forwarded(upstream, path) == []
    assert calls == []


@pytest.mark.parametrize("path", ADDRESS_FLOWS)
@pytest.mark.parametrize("key", ["Email", "EMAIL"])
def test_address_flow_email_key_is_read_ignoring_case(client, upstream, path, key):
    response = client.post(path, json={"method": "code", key: "x@guest.invalid"})
    assert response.status_code == 400
    assert _forwarded(upstream, path) == []


@pytest.mark.parametrize("path", ADDRESS_FLOWS)
@pytest.mark.parametrize("key", ["email", "Email"])
def test_address_flow_to_guest_domain_is_refused_form(client, upstream, monkeypatch, path, key):
    calls = []
    monkeypatch.setattr(courier, "start", lambda: _record(calls))

    response = client.post(path, data={"method": "code", key: " x@Guest.Invalid "})

    assert response.status_code == 400
    assert response.json()["error"]["id"] == "address_not_accepted"
    assert _forwarded(upstream, path) == []
    assert calls == []


@pytest.mark.parametrize("path", ["/auth/self-service/Verification/?flow=f1", "/auth/self-service/recover%79?flow=f1"])
def test_address_flow_other_path_spellings_are_refused(client, upstream, path):
    assert client.post(path, json={"method": "code", "email": "x@guest.invalid"}).status_code == 400
    assert upstream.requests == []


@pytest.mark.parametrize("path", ADDRESS_FLOWS)
@pytest.mark.parametrize("body", [{"json": {"method": "code", "email": "m@example.com"}},
                                  {"data": {"method": "code", "email": "m@example.com"}},
                                  {"json": {"method": "code", "code": "123456"}},
                                  {"json": {"method": "code", "email": "x@guest.invalid.example.com"}},
                                  {"json": {"method": "code", "email": "x@notguest.invalid"}}])
def test_address_flow_other_submissions_are_forwarded(client, upstream, monkeypatch, path, body):
    calls = []
    monkeypatch.setattr(courier, "start", lambda: _record(calls))

    response = client.post(path, **body)

    assert response.status_code == 200
    assert len(_forwarded(upstream, path)) == 1
    assert calls == [True]


@pytest.mark.parametrize("path", ADDRESS_FLOWS)
@pytest.mark.parametrize(
    "content,content_type",
    [
        (b'{"email": "m@example.com", "Email": "x@guest.invalid"}', "application/json"),
        (b"not json", "application/json"),
        (b"email=m%40example.com&Email=x%40guest.invalid", "application/x-www-form-urlencoded"),
        (b"\xff\xfe", "application/x-www-form-urlencoded"),
    ],
    ids=["json_duplicate_key", "json_broken", "form_duplicate_key", "form_not_utf8"],
)
def test_address_flow_unreadable_body_is_400(client, upstream, path, content, content_type):
    response = client.post(path, content=content, headers={"content-type": content_type})
    assert response.status_code == 400
    assert response.json()["error"]["id"] == "invalid_request_body"
    assert upstream.requests == []


@pytest.mark.parametrize("path", ADDRESS_FLOWS)
def test_address_flow_refusal_does_not_depend_on_guest_flag(client, upstream, guest_enabled, path):
    assert client.post(path, json={"method": "code", "email": "x@guest.invalid"}).status_code == 400
    assert upstream.requests == []


# ============ 식별자의 문자 ============

INVALID_IDENTIFIER = {
    "error": {
        "id": "invalid_identifier",
        "code": 400,
        "status": "Bad Request",
        "reason": "로그인 식별자와 이메일에는 ASCII 문자만 쓸 수 있습니다.",
    }
}
# (제출 경로, 식별자의 키) 로그인은 identifier·password_identifier, 가입은 traits.email, 인증·복구는 email
IDENTIFIER_FIELDS = [
    ("/auth/self-service/login?flow=f1", ("identifier",)),
    ("/auth/self-service/login?flow=f1", ("password_identifier",)),
    ("/auth/self-service/registration?flow=f1", ("traits", "email")),
    ("/auth/self-service/verification?flow=f1", ("email",)),
    ("/auth/self-service/recovery?flow=f1", ("email",)),
]
IDENTIFIER_FIELD_IDS = ["login", "login_password_identifier", "registration", "verification", "recovery"]
NON_ASCII_IDENTIFIERS = {
    "fullwidth_letter": "ｍember@example.com",
    "fullwidth_at": "member＠example.com",
    "dotted_capital_i": "İnfo@example.com",
    "no_break_space_before": " member@example.com",
    "ideographic_space_after": "member@example.com　",
    "local_part_letter": "mémber@example.com",
    "domain_letter": "member@exämple.com",
}


def _submission_body(path: str, keys: tuple[str, ...], value: object, form: bool = False) -> dict:
    """keys 자리에 value를 둔 제출 본문. 폼 본문의 키는 keys를 점으로 이은 것이다"""
    method = "password" if "/login" in path or "/registration" in path else "code"
    if form:
        return {"method": method, ".".join(keys): value}
    return {"method": method, keys[0]: value if len(keys) == 1 else {keys[1]: value}}


@pytest.mark.parametrize("path,keys", IDENTIFIER_FIELDS, ids=IDENTIFIER_FIELD_IDS)
@pytest.mark.parametrize("identifier", list(NON_ASCII_IDENTIFIERS.values()), ids=list(NON_ASCII_IDENTIFIERS))
@pytest.mark.parametrize("form", [False, True], ids=["json", "form"])
def test_non_ascii_identifier_is_refused(client, upstream, guest_enabled, siteverify, path, keys, identifier, form):
    body = _submission_body(path, keys, identifier, form)

    response = client.post(
        path, **({"data": body} if form else {"json": body}), headers={"X-Turnstile-Token": "t1"}
    )

    assert response.status_code == 400
    assert response.json() == INVALID_IDENTIFIER
    assert upstream.requests == []
    assert siteverify == []


@pytest.mark.parametrize("path,keys", IDENTIFIER_FIELDS, ids=IDENTIFIER_FIELD_IDS)
@pytest.mark.parametrize("form", [False, True], ids=["json_escape", "form_encoded"])
def test_identifier_with_surrogate_is_refused(client, upstream, guest_enabled, siteverify, path, keys, form):
    if form:
        content_type = "application/x-www-form-urlencoded"
        content = f"{'.'.join(keys)}=member%ED%A0%80%40example.com".encode()
    else:
        content_type = "application/json"
        content = json.dumps(_submission_body(path, keys, "member\ud800@example.com")).encode()
        assert b"\\ud800" in content

    response = client.post(path, content=content, headers={"content-type": content_type, "X-Turnstile-Token": "t1"})

    assert response.status_code == 400
    assert response.json() == INVALID_IDENTIFIER
    assert upstream.requests == []
    assert siteverify == []


@pytest.mark.parametrize("path,keys", IDENTIFIER_FIELDS, ids=IDENTIFIER_FIELD_IDS)
def test_non_ascii_identifier_refusal_does_not_depend_on_guest_flag(client, upstream, path, keys):
    response = client.post(path, json=_submission_body(path, keys, "mémber@example.com"))

    assert response.status_code == 400
    assert response.json() == INVALID_IDENTIFIER
    assert upstream.requests == []


@pytest.mark.parametrize("path,keys", IDENTIFIER_FIELDS, ids=IDENTIFIER_FIELD_IDS)
@pytest.mark.parametrize("identifier", ["member@example.com", "\tMember@Example.COM \n", "x+tag@sub.example.com"])
@pytest.mark.parametrize("form", [False, True], ids=["json", "form"])
def test_ascii_identifier_is_forwarded(client, upstream, guest_enabled, siteverify, path, keys, identifier, form):
    body = _submission_body(path, keys, identifier, form)

    response = client.post(path, **({"data": body} if form else {"json": body}))

    assert response.status_code == 200
    assert len(_forwarded(upstream, path)) == 1
    assert siteverify == []


@pytest.mark.parametrize("path,keys", IDENTIFIER_FIELDS, ids=IDENTIFIER_FIELD_IDS)
@pytest.mark.parametrize("value", [123, True, None, ["mémber@example.com"], {"address": "mémber@example.com"}])
def test_identifier_that_is_not_a_string_is_forwarded(client, upstream, guest_enabled, path, keys, value):
    response = client.post(path, json=_submission_body(path, keys, value))

    assert response.status_code == 200
    assert len(_forwarded(upstream, path)) == 1


@pytest.mark.parametrize(
    "path,content,content_type",
    [
        ("/auth/self-service/login?flow=f1",
         '{"identifier": "mémber@example.com", "Identifier": "member@example.com"}', "application/json"),
        ("/auth/self-service/login?flow=f1",
         '{"identifier": "member@example.com", "password_identifier": "mémber@example.com"}', "application/json"),
        ("/auth/self-service/login?flow=f1",
         "identifier=m%C3%A9mber%40example.com&identifier=member%40example.com", "application/x-www-form-urlencoded"),
        ("/auth/self-service/verification?flow=f1",
         '{"email": "mémber@example.com", "Email": "member@example.com"}', "application/json"),
        ("/auth/self-service/recovery?flow=f1",
         "email=member%40example.com&Email=m%C3%A9mber%40example.com", "application/x-www-form-urlencoded"),
    ],
    ids=["login_json_case", "login_json_two_keys", "login_form_repeated", "verification_json_case",
         "recovery_form_case"],
)
def test_identifier_given_twice_keeps_unreadable_body_answer(client, upstream, guest_enabled, siteverify, path,
                                                             content, content_type):
    response = client.post(path, content=content.encode(), headers={"content-type": content_type})

    assert response.status_code == 400
    assert response.json()["error"]["id"] == "invalid_request_body"
    assert upstream.requests == []


@pytest.mark.parametrize(
    "value,normalized",
    [
        ("Member@Example.COM", "member@example.com"),
        (" \t\n\v\f\rmember@example.com\r\f\v\n\t ", "member@example.com"),
        ("\x1cmember@example.com\x1f", "\x1cmember@example.com\x1f"),
        ("mem ber@example.com", "mem ber@example.com"),
    ],
    ids=["case", "ascii_spaces", "other_control_characters", "inner_space"],
)
def test_normalize_identifier_trims_ascii_spaces_and_lowercases(value, normalized):
    """Kratos(Go strings.ToLower(strings.TrimSpace(v)))와 같다. TrimSpace는 U+001C~U+001F를 떼지 않는다"""
    assert auth_proxy.normalize_identifier(value) == normalized


def test_unbuildable_url_is_answered_before_identifier_check(client, upstream):
    response = client.post(
        "/auth/self-service/login%00?flow=f1", json={"method": "password", "identifier": "mémber@example.com"}
    )

    assert response.status_code == 400
    assert response.json() == INVALID_REQUEST_URL
    assert upstream.requests == []


def test_identifier_check_comes_before_query_check(client, upstream):
    response = client.post(
        "/auth/self-service/recovery?flow=f1&x=1", json={"method": "code", "email": "mémber@example.com"}
    )

    assert response.status_code == 400
    assert response.json() == INVALID_IDENTIFIER
    assert upstream.requests == []


def test_get_submission_values_are_not_checked_as_identifier(client, upstream, guest_enabled):
    refused = client.get("/auth/self-service/login?flow=f1&identifier=m%C3%A9mber%40example.com")
    forwarded = client.get("/auth/self-service/verification?flow=f1&code=%C3%A9")

    assert refused.status_code == 400
    assert refused.json()["error"]["id"] == "invalid_request_body"
    assert forwarded.status_code == 200
    assert len(upstream.requests) == 1


# ============ 검사하는 제출의 쿼리 문자열 ============

@pytest.mark.parametrize(
    "path,body",
    [
        ("/auth/self-service/verification?flow=f1&email=x%40guest.invalid", {"method": "code"}),
        ("/auth/self-service/recovery?flow=f1&email=x%40guest.invalid", {"method": "code"}),
        ("/auth/self-service/verification?Email=x%40guest.invalid&flow=f1", {"method": "code"}),
        ("/auth/self-service/settings?flow=f1&method=password", {"method": "password", "password": "x"}),
        ("/auth/self-service/settings?flow=f1&password=New-Pass-123", {"method": "password"}),
        ("/auth/self-service/settings?flow=f1&traits.name=%EC%B2%A0%EC%88%98", {"method": "profile"}),
        ("/auth/self-service/registration?flow=f1&traits.email=a%40b.c", {"method": "oidc", "provider": "google"}),
        ("/auth/self-service/login?flow=f1&identifier=a%40b.c", {"method": "password"}),
        ("/auth/self-service/login?flow=f1&flow=f2", {"method": "password"}),
        ("/auth/self-service/login?flow=f1&Flow=f2", {"method": "password"}),
        ("/auth/self-service/login?flow=f1&=x", {"method": "password"}),
        ("/auth/Self-Service/Recovery/?flow=f1&email=x%40guest.invalid", {"method": "code"}),
    ],
)
def test_inspected_submission_with_other_query_keys_is_refused(client, upstream, monkeypatch, path, body):
    calls = []
    monkeypatch.setattr(courier, "start", lambda: _record(calls))

    response = client.post(path, json=body, headers={"X-Session-Token": "ory_st_x"})

    assert response.status_code == 400
    assert response.json()["error"]["id"] == "invalid_request_body"
    assert upstream.requests == []
    assert calls == []


@pytest.mark.parametrize(
    "path",
    [
        "/auth/self-service/verification?flow=f1",
        "/auth/self-service/recovery?flow=f1",
        "/auth/self-service/login?flow=f1",
        "/auth/self-service/registration?flow=f1",
        "/auth/self-service/login?Flow=f1",
        "/auth/self-service/login",
    ],
)
def test_inspected_submission_with_only_flow_is_forwarded(client, upstream, path):
    response = client.post(path, json={"method": "code"})
    assert response.status_code == 200
    assert len(upstream.requests) == 1


@pytest.mark.parametrize(
    "path",
    [
        "/auth/sessions/whoami?tokenize_as=api",
        "/auth/self-service/login/api?return_to=https%3A%2F%2Fapp.example.com&refresh=true",
        "/auth/self-service/registration/api?return_to=x",
        "/auth/self-service/settings/api",
        "/auth/self-service/settings/flows?id=f1",
        "/auth/sessions/token-exchange?init_code=c1&return_to_code=c2",
        "/auth/self-service/methods/oidc/callback/google?code=c1&state=s1",
    ],
)
def test_get_requests_keep_their_query(client, upstream, path):
    response = client.get(path)
    assert response.status_code == 200
    assert upstream.requests[0].url.path == path.split("?", 1)[0].removeprefix("/auth")
    assert upstream.requests[0].url.query.decode() == (path.split("?", 1)[1] if "?" in path else "")


def test_other_post_paths_keep_their_query(client, upstream):
    response = client.post("/auth/self-service/logout/api?x=1", json={"session_token": "ory_st_abc"})
    assert response.status_code == 200
    assert upstream.requests[0].url.query == b"x=1"


# ============ 검사하는 제출 경로의 GET ============

PROXY_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]
SUBMIT_PATHS = [
    "/auth/self-service/settings",
    "/auth/self-service/login",
    "/auth/self-service/registration",
    "/auth/self-service/verification",
    "/auth/self-service/recovery",
]


def send(client, method, path):
    """GET은 본문 없이, 나머지는 JSON 본문을 붙여 세션 토큰과 함께 보낸다"""
    body = None if method == "GET" else {"method": "password", "password": "New-Pass-123"}
    return client.request(method, path, json=body, headers={"X-Session-Token": "ory_st_x"})


@pytest.mark.parametrize("method", PROXY_METHODS)
@pytest.mark.parametrize("path", SUBMIT_PATHS)
@pytest.mark.parametrize(
    "query", ["flow=f1&method=password", "method=password", "flow=f1&x=1", "flow=f1&flow=f2", "flow=f1&=x"]
)
def test_submit_path_with_other_query_keys_is_refused_for_every_method(
        client, upstream, monkeypatch, method, path, query
):
    calls = []
    monkeypatch.setattr(courier, "start", lambda: _record(calls))
    kratos_with_session(upstream, RECOVERY_SESSION)

    response = send(client, method, f"{path}?{query}")

    assert response.status_code == 400
    assert response.json()["error"]["id"] == "invalid_request_body"
    assert upstream.requests == []
    assert calls == []


@pytest.mark.parametrize("method", PROXY_METHODS)
@pytest.mark.parametrize("path", SUBMIT_PATHS)
@pytest.mark.parametrize("query", ["flow=f1", "Flow=f1", "FLOW=f1", ""])
def test_submit_path_with_only_flow_or_no_query_is_forwarded_for_every_method(client, upstream, method, path, query):
    kratos_with_session(upstream, RECOVERY_SESSION)

    response = send(client, method, f"{path}?{query}" if query else path)

    assert response.status_code == 200
    forwarded = [r for r in upstream.requests if r.url.path != "/sessions/whoami"]
    assert len(forwarded) == 1
    assert forwarded[0].method == method
    assert forwarded[0].url.path == path.removeprefix("/auth")
    assert forwarded[0].url.query.decode() == query


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize(
    "path",
    [
        "/auth/self-service/Settings?flow=f1&method=password",
        "/auth/self-service/settings/?flow=f1&method=password",
        "/auth/self-service/%73ettings?flow=f1&method=password",
        "/auth/self-service/x/../settings?flow=f1&method=password",
        "/auth/self-service/settings%2F?flow=f1&method=password",
        "/auth/self-service/settings%3Fmethod=password",
        "/auth/self-service/LOGIN/?flow=f1&identifier=user%40example.com",
        "/auth/x/../self-service/login?flow=f1&identifier=user%40example.com",
        "/auth/self-service/Registration?flow=f1&traits.email=user%40example.com",
        "/auth/self-service/Verification/?flow=f1&email=user%40example.com",
        "/auth/self-service/recover%79?flow=f1&email=user%40example.com",
    ],
)
def test_submit_path_spellings_are_checked_as_sent(client, upstream, method, path):
    """경로를 바꿔 써도 Kratos로 나갈 경로·쿼리 기준으로 검사한다"""
    kratos_with_session(upstream, RECOVERY_SESSION)

    response = send(client, method, path)

    assert response.status_code == 400
    assert upstream.requests == []


@pytest.mark.parametrize(
    "query",
    [
        "flow=f1&method=password",
        "flow=f1&password=New-Pass-123",
        "flow=f1&traits.email=user%40example.com",
        "flow=f1&link=google",
        "flow=f1&Method=profile",
    ],
)
def test_settings_get_with_submit_values_is_refused(client, upstream, query):
    kratos_with_session(upstream, RECOVERY_SESSION)

    response = client.get(f"/auth/self-service/settings?{query}", headers={"X-Session-Token": "ory_st_x"})

    assert response.status_code == 400
    assert response.json()["error"]["id"] == "invalid_request_body"
    assert upstream.requests == []


@pytest.mark.parametrize("query", ["flow=f1&code=123456", "code=123456&flow=f1", "FLOW=f1&Code=123456", "flow=f1"])
def test_verification_link_is_forwarded_with_its_query(client, upstream, query):
    response = client.get(f"/auth/self-service/verification?{query}")

    assert response.status_code == 200
    [sent] = upstream.requests
    assert sent.method == "GET"
    assert sent.url.path == "/self-service/verification"
    assert sent.url.query.decode() == query


@pytest.mark.parametrize(
    "query",
    [
        "flow=f1&code=123456&email=user%40example.com",
        "flow=f1&code=123456&method=code",
        "flow=f1&email=user%40example.com",
        "flow=f1&method=code",
        "flow=f1&code=1&code=2",
        "flow=f1&code=1&Code=2",
    ],
)
def test_verification_get_with_other_query_keys_is_refused(client, upstream, query):
    response = client.get(f"/auth/self-service/verification?{query}")

    assert response.status_code == 400
    assert response.json()["error"]["id"] == "invalid_request_body"
    assert upstream.requests == []


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/auth/self-service/verification"),
        ("GET", "/auth/self-service/recovery"),
        ("GET", "/auth/self-service/login"),
        ("GET", "/auth/self-service/registration"),
        ("GET", "/auth/self-service/settings"),
    ],
)
def test_code_in_query_is_accepted_only_on_verification_get(client, upstream, method, path):
    kratos_with_session(upstream, RECOVERY_SESSION)

    response = send(client, method, f"{path}?flow=f1&code=123456")

    assert response.status_code == 400
    assert upstream.requests == []


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_submission_that_did_not_pass_the_interceptor_is_not_forwarded(upstream, method):
    app = FastAPI()
    app.include_router(auth_proxy.router)
    client = TestClient(app, raise_server_exceptions=False)

    response = send(client, method, "/auth/self-service/settings?flow=f1")

    assert response.status_code == 500
    assert upstream.requests == []


@pytest.mark.asyncio
async def test_chunked_large_submission_is_forwarded_byte_identical(upstream):
    app = FastAPI()
    app.add_middleware(GuestGateMiddleware)
    app.include_router(auth_proxy.router)
    payload = json.dumps(
        {"method": "password", "identifier": "member@example.com", "password": "p" * 300_000}
    ).encode()

    async def chunks():
        for start in range(0, len(payload), 7000):
            yield payload[start:start + 7000]

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/auth/self-service/login?flow=f1", content=chunks(), headers={"content-type": "application/json"}
        )

    assert response.status_code == 200
    [sent] = upstream.requests
    assert sent.content == payload


# ============ 검사하는 제출의 본문 형식 ============

FORM_TYPE = "application/x-www-form-urlencoded"
MULTIPART_TYPE = "multipart/form-data; boundary=b0"
# (검사하는 제출 경로, 그 경로에서 Kratos로 넘어가는 method)
BODY_SUBMITS = [
    ("/auth/self-service/login?flow=f1", "password"),
    ("/auth/self-service/registration?flow=f1", "password"),
    ("/auth/self-service/settings?flow=f1", "password"),
    ("/auth/self-service/verification?flow=f1", "code"),
    ("/auth/self-service/recovery?flow=f1", "code"),
]
BODY_SUBMIT_IDS = ["login", "registration", "settings", "verification", "recovery"]


def _multipart(fields: dict[str, str]) -> bytes:
    parts = [f'--b0\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n' for k, v in fields.items()]
    return ("".join(parts) + "--b0--\r\n").encode()


# (본문, Content-Type) METHOD 자리에 경로의 method를 넣는다. Content-Type이 None이면 헤더를 붙이지 않는다
REFUSED_BODIES = {
    "json_dotted_key": (b'{"method": "METHOD", "traits.email": "a@example.com"}', "application/json"),
    "json_other_dotted_key": (b'{"method": "METHOD", "transient_payload.x": "1"}', "application/json"),
    "json_traits_string": (b'{"method": "METHOD", "traits": "{\\"email\\": \\"a@example.com\\"}"}', "application/json"),
    "json_traits_key_case_string": (b'{"method": "METHOD", "Traits": "{}"}', "application/json"),
    "json_traits_list": (b'{"method": "METHOD", "traits": ["a@example.com"]}', "application/json"),
    "json_traits_null": (b'{"method": "METHOD", "traits": null}', "application/json"),
    "json_duplicate_key": (b'{"method": "METHOD", "method": "METHOD"}', "application/json"),
    "json_case_duplicate_key": (b'{"method": "METHOD", "Method": "METHOD"}', "application/json"),
    "json_nested_duplicate_key": (b'{"method": "METHOD", "traits": {"email": "a@b.c", "Email": "d@e.f"}}',
                                  "application/json"),
    "json_array": (b'[{"method": "METHOD"}]', "application/json"),
    "json_string": (b'"METHOD"', "application/json"),
    "json_broken": (b'{"method": "METHOD"', "application/json"),
    "json_deeply_nested": (b'{"method": "METHOD", "x": ' + b"[" * 100000 + b"]" * 100000 + b"}", "application/json"),
    "json_empty": (b"", "application/json"),
    "json_not_utf8": (b'{"method": "METHOD", "x": "\xff"}', "application/json"),
    "form_traits": (b"method=METHOD&traits=%7B%22email%22%3A%22a%40example.com%22%7D", FORM_TYPE),
    "form_traits_key_case": (b"method=METHOD&TRAITS=%7B%7D", FORM_TYPE),
    "form_traits_key_encoded": (b"method=METHOD&%74raits=%7B%7D", FORM_TYPE),
    "form_traits_without_value": (b"method=METHOD&traits", FORM_TYPE),
    "form_repeated_key": (b"method=METHOD&method=METHOD", FORM_TYPE),
    "form_case_repeated_key": (b"method=METHOD&Method=METHOD", FORM_TYPE),
    "form_not_utf8": (b"method=METHOD&x=\xff", FORM_TYPE),
    "multipart": (_multipart({"method": "METHOD", "traits.email": "a@example.com"}), MULTIPART_TYPE),
    "text_plain": (b'{"method": "METHOD"}', "text/plain"),
    "octet_stream": (b'{"method": "METHOD"}', "application/octet-stream"),
    "no_content_type": (b'{"method": "METHOD"}', None),
    "json_suffix_type": (b'{"method": "METHOD"}', "application/merge-patch+json"),
    "two_media_types": (b'{"method": "METHOD"}', "application/json, application/x-www-form-urlencoded"),
}
ACCEPTED_BODIES = {
    "json": (b'{"method": "METHOD", "traits": {"email": "a@example.com", "name": "A"}}', "application/json"),
    "json_without_traits": (b'{"method": "METHOD", "email": "a@example.com"}', "application/json"),
    "json_charset": (b'{"method": "METHOD"}', "application/json; charset=utf-8"),
    "json_media_type_case": (b'{"method": "METHOD"}', " Application/JSON "),
    "form": (b"method=METHOD&traits.email=a%40example.com&traits.name=A", FORM_TYPE),
    "form_charset": (b"method=METHOD&email=a%40example.com", "application/x-www-form-urlencoded; charset=UTF-8"),
    "form_media_type_case": (b"method=METHOD", "Application/X-WWW-Form-Urlencoded"),
}


def _post_body(client, path, method, content, content_type, http_method="POST"):
    headers = {"X-Session-Token": "ory_st_recovery"}
    if content_type is not None:
        headers["Content-Type"] = content_type
    return client.request(http_method, path, content=content.replace(b"METHOD", method.encode()), headers=headers)


@pytest.mark.parametrize("path,method", BODY_SUBMITS, ids=BODY_SUBMIT_IDS)
@pytest.mark.parametrize("content,content_type", list(REFUSED_BODIES.values()), ids=list(REFUSED_BODIES))
def test_submission_body_in_other_representation_is_400_and_not_forwarded(
        client, upstream, monkeypatch, path, method, content, content_type
):
    calls = []
    monkeypatch.setattr(courier, "start", lambda: _record(calls))
    kratos_with_session(upstream, RECOVERY_SESSION)

    response = _post_body(client, path, method, content, content_type)

    assert response.status_code == 400
    assert response.json()["error"]["id"] == "invalid_request_body"
    assert upstream.requests == []
    assert calls == []


@pytest.mark.parametrize("path,method", BODY_SUBMITS, ids=BODY_SUBMIT_IDS)
@pytest.mark.parametrize("content,content_type", list(ACCEPTED_BODIES.values()), ids=list(ACCEPTED_BODIES))
def test_submission_body_in_read_representation_is_forwarded_unchanged(
        client, upstream, path, method, content, content_type
):
    kratos_with_session(upstream, RECOVERY_SESSION)

    response = _post_body(client, path, method, content, content_type)

    assert response.status_code == 200
    [sent] = [r for r in upstream.requests if r.url.path != "/sessions/whoami"]
    assert sent.url.path == path.split("?")[0].removeprefix("/auth")
    assert sent.content == content.replace(b"METHOD", method.encode())


@pytest.mark.parametrize("http_method", ["PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("path,method", BODY_SUBMITS, ids=BODY_SUBMIT_IDS)
def test_submission_body_rule_applies_to_every_method_other_than_get(client, upstream, http_method, path, method):
    kratos_with_session(upstream, RECOVERY_SESSION)
    content, content_type = REFUSED_BODIES["json_dotted_key"]

    response = _post_body(client, path, method, content, content_type, http_method=http_method)

    assert response.status_code == 400
    assert response.json()["error"]["id"] == "invalid_request_body"
    assert upstream.requests == []


@pytest.mark.parametrize(
    "path",
    [
        "/auth/self-service/Registration/?flow=f1",
        "/auth/self-service/recover%79?flow=f1",
        "/auth/self-service/x/../settings?flow=f1",
        "/auth/self-service/LOGIN",
    ],
)
def test_submission_body_rule_applies_to_submit_path_spellings(client, upstream, path):
    kratos_with_session(upstream, RECOVERY_SESSION)
    content, content_type = REFUSED_BODIES["json_dotted_key"]

    response = _post_body(client, path, "password", content, content_type)

    assert response.status_code == 400
    assert response.json()["error"]["id"] == "invalid_request_body"
    assert upstream.requests == []


@pytest.mark.parametrize("path,method", BODY_SUBMITS, ids=BODY_SUBMIT_IDS)
@pytest.mark.parametrize("name", ["json_dotted_key", "form_traits", "multipart", "text_plain"])
def test_submission_body_rule_does_not_depend_on_guest_flag(client, upstream, guest_enabled, siteverify, path, method,
                                                            name):
    kratos_with_session(upstream, RECOVERY_SESSION)
    content, content_type = REFUSED_BODIES[name]

    response = _post_body(client, path, method, content, content_type)

    assert response.status_code == 400
    assert response.json()["error"]["id"] == "invalid_request_body"
    assert upstream.requests == []
    assert siteverify == []


@pytest.mark.parametrize("flow", ["registration", "login"])
@pytest.mark.parametrize(
    "content,content_type",
    [
        (b'{"method": "oidc", "provider": "google", "traits": "{\\"email\\": \\"other@example.com\\"}"}',
         "application/json"),
        (b'{"method": "oidc", "provider": "google", "traits.email": "other@example.com"}', "application/json"),
        (b"method=oidc&provider=google&traits=%7B%22email%22%3A%22other%40example.com%22%7D", FORM_TYPE),
        (_multipart({"method": "oidc", "provider": "google", "traits.email": "other@example.com"}), MULTIPART_TYPE),
        (b'{"method": "oidc", "provider": "google", "traits": {"email": "other@example.com"}}', "text/plain"),
    ],
    ids=["json_traits_string", "json_dotted_key", "form_traits", "multipart", "text_plain"],
)
def test_oidc_submit_in_other_representation_is_400_and_not_forwarded(client, upstream, flow, content, content_type):
    response = client.post(
        f"/auth/self-service/{flow}?flow=f1", content=content, headers={"Content-Type": content_type}
    )

    assert response.status_code == 400
    assert response.json()["error"]["id"] == "invalid_request_body"
    assert upstream.requests == []


def test_submission_body_rule_comes_before_identifier_rule(client, upstream):
    response = client.post(
        "/auth/self-service/login?flow=f1",
        json={"method": "password", "identifier": "mémber@example.com", "traits.email": "member@example.com"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["id"] == "invalid_request_body"
    assert upstream.requests == []


@pytest.mark.parametrize("path,method", BODY_SUBMITS, ids=BODY_SUBMIT_IDS)
@pytest.mark.parametrize("name", ["json_dotted_key", "form_traits", "multipart", "text_plain", "json_broken"])
def test_get_submission_body_is_not_checked(client, upstream, path, method, name):
    content, content_type = REFUSED_BODIES[name]

    response = _post_body(client, path, method, content, content_type, http_method="GET")

    assert response.status_code == 200
    [sent] = upstream.requests
    assert sent.method == "GET"
    assert sent.url.path == path.split("?")[0].removeprefix("/auth")


@pytest.mark.parametrize(
    "path",
    [
        "/auth/self-service/logout/api",
        "/auth/self-service/login/api",
        "/auth/self-service/methods/oidc/callback/google",
        "/auth/unknown",
    ],
)
@pytest.mark.parametrize("name", ["json_dotted_key", "form_traits", "form_repeated_key", "multipart", "text_plain"])
def test_other_paths_forward_any_body_unchanged(client, upstream, path, name):
    content, content_type = REFUSED_BODIES[name]
    content = content.replace(b"METHOD", b"password")

    response = client.post(path, content=content, headers={"Content-Type": content_type})

    assert response.status_code == 200
    [sent] = upstream.requests
    assert sent.url.path == path.removeprefix("/auth")
    assert sent.content == content
    assert sent.headers["content-type"] == content_type


# ============ Kratos URL을 만들 수 없는 요청 ============

INVALID_REQUEST_URL = {
    "error": {"id": "invalid_request_url", "code": 400, "status": "Bad Request", "reason": "요청 주소를 읽을 수 없습니다."}
}


@pytest.mark.parametrize("method", PROXY_METHODS)
@pytest.mark.parametrize(
    "path",
    [
        "/auth/self-service/login%00",
        "/auth/self-service/login%09?flow=f1",
        "/auth/self-service/settings%00?flow=f1",
        "/auth/self-service/verification%09?flow=f1&code=123456",
        "/auth/self-service/login%3Fflow=%09",
        "/auth/sessions/whoami%00",
        "/auth/self-service/login/api%09",
        "/auth/sessions/whoami%3Ftokenize_as=%00",
    ],
)
def test_request_with_control_character_in_kratos_url_is_400(client, upstream, method, path):
    kratos_with_session(upstream, RECOVERY_SESSION)

    response = send(client, method, path)

    assert response.status_code == 400
    assert response.json() == INVALID_REQUEST_URL
    assert upstream.requests == []


async def _send_raw_query(app, method: str, path: str, query_string: bytes) -> tuple[int, dict]:
    """query_string을 바이트 그대로 담은 ASGI 요청을 보낸다 (HTTP 클라이언트는 제어 문자가 든 URL을 만들지 않는다)"""
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": query_string,
        "headers": [(b"host", b"testserver"), (b"content-type", b"application/json")],
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
    }
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"{}", "more_body": False}

    async def send_message(message):
        messages.append(message)

    await app(scope, receive, send_message)
    start = next(m for m in messages if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return start["status"], json.loads(body)


@pytest.mark.asyncio
@pytest.mark.parametrize("method", PROXY_METHODS)
@pytest.mark.parametrize("path", ["/auth/self-service/login", "/auth/sessions/whoami"])
@pytest.mark.parametrize("query_string", [b"flow=f1\x00", b"flow=\x7ff1"])
async def test_request_with_control_character_in_query_is_400(client, upstream, method, path, query_string):
    status, body = await _send_raw_query(client.app, method, path, query_string)

    assert status == 400
    assert body == INVALID_REQUEST_URL
    assert upstream.requests == []


@pytest.mark.parametrize("method", PROXY_METHODS)
@pytest.mark.parametrize("path", ["/auth/self-service/login", "/auth/self-service/settings", "/auth/sessions/whoami"])
def test_request_whose_kratos_url_is_too_long_is_400(client, upstream, method, path):
    """httpx는 65536자를 넘는 URL을 만들지 않는다"""
    kratos_with_session(upstream, RECOVERY_SESSION)
    body = None if method == "GET" else {"method": "password", "password": "New-Pass-123"}

    response = client.request(
        method, path, params={"flow": "f" * 65_520}, json=body, headers={"X-Session-Token": "ory_st_x"}
    )

    assert response.status_code == 400
    assert response.json() == INVALID_REQUEST_URL
    assert upstream.requests == []


def test_full_app_refusal_of_unbuildable_url_carries_cors_headers(app_client, upstream):
    response = app_client.post(
        "/auth/self-service/login%00?flow=f1",
        json={"method": "password", "identifier": "member@example.com", "password": "x"},
        headers={"Origin": "http://localhost:3000"},
    )

    assert response.status_code == 400
    assert response.json() == INVALID_REQUEST_URL
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert upstream.requests == []


def test_full_app_refusal_of_non_ascii_identifier_carries_cors_headers(app_client, upstream):
    response = app_client.post(
        "/auth/self-service/login?flow=f1",
        json={"method": "password", "identifier": "mémber@example.com", "password": "x"},
        headers={"Origin": "http://localhost:3000"},
    )

    assert response.status_code == 400
    assert response.json() == INVALID_IDENTIFIER
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert upstream.requests == []


# ============ KRATOS_PUBLIC_URL의 경로 ============

# (KRATOS_PUBLIC_URL, Kratos로 나가는 경로의 접두사)
BASE_URLS = [
    ("http://kratos.test", ""),
    ("http://kratos.test/", ""),
    ("http://kratos.test/kratos", "/kratos"),
    ("http://kratos.test/kratos/", "/kratos"),
]


@pytest.fixture(params=BASE_URLS, ids=[url for url, _ in BASE_URLS])
def base_path(request, upstream, monkeypatch):
    """KRATOS_PUBLIC_URL을 바꾸고(GUEST_ENABLED) Kratos로 나가는 경로의 접두사를 돌려준다"""
    base_url, prefix = request.param
    monkeypatch.setattr(auth_proxy, "settings", Settings(KRATOS_PUBLIC_URL=base_url, GUEST_ENABLED=True,
                                                         KRATOS_ADMIN_URL="http://admin.test",
                                                         KRATOS_HOOK_API_KEY="k", TURNSTILE_SECRET_KEY="s"))
    monkeypatch.setattr(
        auth_proxy,
        "_make_client",
        lambda: httpx.AsyncClient(base_url=base_url, transport=httpx.MockTransport(upstream)),
    )
    return prefix


@pytest.fixture
def siteverify(monkeypatch):
    """Turnstile 확인을 통과시키고 받은 토큰을 기록한다"""
    tokens = []

    async def verify(token):
        tokens.append(token)
        return True

    monkeypatch.setattr(turnstile, "verify", verify)
    return tokens


@pytest.fixture
def rate_limited(upstream, monkeypatch):
    from app.ratelimit.limiter import reset_limiter
    from app.ratelimit.storage.memory import reset_storage

    monkeypatch.setattr(app_config.settings, "RATE_LIMIT_ENABLED", True)
    # 클라이언트 IP는 프록시 설정 없이 request.client.host로 센다
    monkeypatch.setattr(app_config.settings, "PROXY_FORCE", False)
    monkeypatch.setattr(app_config.settings, "CF_ENABLED", False)
    reset_storage()
    reset_limiter()
    yield
    reset_storage()
    reset_limiter()


def sent_requests(upstream) -> list[tuple[str, str, str]]:
    return [(r.method, r.url.path, r.url.query.decode()) for r in upstream.requests]


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_settings_query_rule_applies_under_base_url(client, upstream, base_path, method):
    kratos_with_session(upstream, RECOVERY_SESSION, base_path=base_path)

    refused = send(client, method, "/auth/self-service/settings?flow=f1&method=password")
    forwarded = send(client, method, "/auth/self-service/settings?flow=f1")

    assert refused.status_code == 400
    assert refused.json()["error"]["id"] == "invalid_request_body"
    assert forwarded.status_code == 200
    whoami = [] if method == "GET" else [("GET", f"{base_path}/sessions/whoami", "")]
    assert sent_requests(upstream) == [*whoami, (method, f"{base_path}/self-service/settings", "flow=f1")]


def test_settings_session_check_applies_under_base_url(client, upstream, base_path):
    kratos_with_session(upstream, PASSWORD_SESSION, base_path=base_path)

    response = client.post(
        SETTINGS_SUBMIT, json={"method": "password", "password": "New-Pass-123"}, headers={"X-Session-Token": "ory_st_x"}
    )

    assert response.status_code == 403
    assert response.json()["error"]["id"] == "settings_require_email_recovery"
    assert sent_requests(upstream) == [("GET", f"{base_path}/sessions/whoami", "")]


def test_guest_handle_login_needs_token_under_base_url(client, upstream, base_path, siteverify):
    body = {"method": "password", "identifier": "g1@guest.invalid", "password": "1234"}

    refused = client.post("/auth/self-service/login?flow=f1", json=body)
    forwarded = client.post("/auth/self-service/login?flow=f1", json=body, headers={"X-Turnstile-Token": "t1"})

    assert refused.status_code == 403
    assert refused.json()["error"]["id"] == "guest_verification_failed"
    assert forwarded.status_code == 200
    assert siteverify == ["t1"]
    assert sent_requests(upstream) == [("POST", f"{base_path}/self-service/login", "flow=f1")]


def test_get_submission_is_counted_under_base_url(client, upstream, base_path, rate_limited):
    limit = AUTH_SUBMIT_PER_IP.max_requests

    statuses = [client.get("/auth/self-service/login?flow=f1").status_code for _ in range(limit + 1)]

    assert statuses == [200] * limit + [429]
    assert sent_requests(upstream) == [("GET", f"{base_path}/self-service/login", "flow=f1")] * limit


def test_verification_link_under_base_url(client, upstream, base_path):
    forwarded = client.get("/auth/self-service/verification?flow=f1&code=123456")
    refused = client.get("/auth/self-service/verification?flow=f1&code=123456&email=user%40example.com")

    assert forwarded.status_code == 200
    assert refused.status_code == 400
    assert sent_requests(upstream) == [("GET", f"{base_path}/self-service/verification", "flow=f1&code=123456")]


@pytest.mark.parametrize(
    "path", ["/auth/sessions/whoami?tokenize_as=api", "/auth/self-service/login/api?refresh=true", "/auth/health/ready"]
)
def test_other_get_is_forwarded_under_base_url(client, upstream, base_path, path):
    request_path, _, query = path.removeprefix("/auth").partition("?")

    response = client.get(path)

    assert response.status_code == 200
    assert sent_requests(upstream) == [("GET", f"{base_path}{request_path}", query)]


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize(
    "path",
    [
        "/auth/self-service/Settings/?flow=f1&method=password",
        "/auth/self-service/%73ettings?flow=f1&method=password",
        "/auth/self-service/x/%2e%2e/settings?flow=f1&method=password",
        "/auth/%2e%2e/self-service/settings?flow=f1&method=password",
        "/auth/self-service%2Fsettings?flow=f1&method=password",
        "/auth/self-service/settings%3Fmethod=password",
        "/auth/%2e%2e/%2e%2e/self-service/login?flow=f1&identifier=user%40example.com",
        "/auth/self-service/recover%79/?flow=f1&email=user%40example.com",
    ],
)
def test_submit_path_spellings_are_checked_under_base_url(client, upstream, base_path, method, path):
    kratos_with_session(upstream, RECOVERY_SESSION, base_path=base_path)

    response = send(client, method, path)

    assert response.status_code == 400
    assert upstream.requests == []


@pytest.mark.parametrize(
    "method,path,request_path,query",
    [
        ("GET", "/auth/%2e%2e/%2e%2e/sessions/whoami?tokenize_as=api", "/sessions/whoami", "tokenize_as=api"),
        ("GET", "/auth/sessions/x/%2e%2e/%2e%2e/%2e%2e/whoami", "/whoami", ""),
        ("GET", "/auth/self-service/%2e%2e/%2e%2e/self-service/login?flow=f1", "/self-service/login", "flow=f1"),
        ("POST", "/auth/%2e%2e/self-service/login?flow=f1", "/self-service/login", "flow=f1"),
        ("POST", "/auth/self-service/log%69n/?flow=f1", "/self-service/login/", "flow=f1"),
    ],
)
def test_path_spellings_are_sent_under_base_url(client, upstream, base_path, method, path, request_path, query):
    body = None if method == "GET" else {"method": "password", "identifier": "member@example.com", "password": "x"}

    response = client.request(method, path, json=body)

    assert response.status_code == 200
    assert sent_requests(upstream) == [(method, f"{base_path}{request_path}", query)]
