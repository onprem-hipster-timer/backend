"""게스트 단계의 Cloudflare Turnstile 확인 (app/middleware/guest_gate.py, app/core/turnstile.py)

게스트 단계(이름 찾기, 생성, 자기 삭제, 게스트 handle 로그인, 게스트 세션의 설정 제출)는 X-Turnstile-Token 헤더의
토큰이 확인을 통과해야 라우트와 Kratos에 닿는다. 로그인 제출의 게스트 handle 판정은 test_guest_login_turnstile.py.
"""
import asyncio
import uuid
from urllib.parse import parse_qs

import httpx
import pytest

import app.core.config as app_config
from app.core import kratos_slots
from app.core import turnstile as turnstile_client
from app.domain.guest.host import GuestHostStatus
from tests.domain.guest.fakes import TURNSTILE_SECRET, TURNSTILE_VERIFY
from tests.domain.guest.helpers import guest_rows, make_guest

CREATE = "/v1/guests"
LOOKUP = "/v1/guests/lookup"
ME = "/v1/guests/me"
LOGIN = "/auth/self-service/login"
SETTINGS = "/auth/self-service/settings"
TOKEN_HEADER = "X-Turnstile-Token"
WIDGET_TOKEN = "token-from-widget"

V1_STEPS = ["lookup", "create", "delete"]
AUTH_STEPS = ["login", "rename"]
STEPS = V1_STEPS + AUTH_STEPS


@pytest.fixture
def resource(host):
    resource_id = uuid.uuid4()
    host.statuses[resource_id] = GuestHostStatus.OPEN
    return resource_id


@pytest.fixture
def guest(kratos, resource):
    return make_guest(kratos, resource, name="민수", password="1234")


class Step:
    """게스트 단계 요청을 보내고, 그 요청이 라우트나 Kratos에 닿았는지 본다"""

    def __init__(self, name, client, kratos, tokens, guest, resource):
        self.name = name
        self.client = client
        self.kratos = kratos
        self.tokens = tokens
        self.guest = guest
        self.resource = resource
        self.handle = kratos.identities[guest.identity_id]["traits"]["handle"]
        self.session = f"token-{guest.identity_id}"
        kratos.sessions[self.session] = guest.identity_id

    def send(self, token=WIDGET_TOKEN, headers=None, path=None, method=None, follow_redirects=True):
        headers = {**({TOKEN_HEADER: token} if token is not None else {}), **(headers or {})}
        target = {"lookup": LOOKUP, "create": CREATE, "delete": ME, "login": LOGIN, "rename": SETTINGS}[self.name]
        target = path or target
        if self.name in AUTH_STEPS:
            target = f"{target}?flow={uuid.uuid4()}"
        body = None
        if self.name == "lookup":
            body = {"resource_type": "meeting", "resource_id": str(self.resource), "name": "민수"}
        elif self.name == "create":
            body = {"resource_type": "meeting", "resource_id": str(self.resource), "name": "영희", "password": "1234"}
        elif self.name == "delete":
            headers = {**self.tokens.guest(self.guest.identity_id), **headers}
        elif self.name == "login":
            body = {"method": "password", "identifier": self.handle, "password": "1234"}
        else:
            body = {"method": "profile", "traits": {"handle": self.handle, "name": "철수"}}
            headers = {"X-Session-Token": self.session, **headers}
        default_method = {"delete": "DELETE"}.get(self.name, "POST")
        return self.client.request(
            method or default_method, target, json=body, headers=headers, follow_redirects=follow_redirects
        )

    def reached(self, response) -> bool:
        """이름 찾기는 handle을 답했는지, 나머지는 Kratos에 그 일이 닿았는지"""
        if self.name == "lookup":
            return response.status_code == 200 and response.json()["handle"] == self.handle
        if self.name == "create":
            return len(self.kratos.identities) > 1 or len(guest_rows()) > 1
        if self.name == "delete":
            return self.kratos.deleted != [] or guest_rows() == []
        submit_path = "/self-service/login" if self.name == "login" else "/self-service/settings"
        return any(r.method != "GET" and r.url.path == submit_path for r in self.kratos.public_requests)

    def effects(self) -> tuple:
        """Kratos와 게스트 행에 남은 것 (identity 수, 지운 identity, 게스트 행 수, Kratos가 받은 제출 수)"""
        submits = sum(r.method != "GET" for r in self.kratos.public_requests)
        return len(self.kratos.identities), list(self.kratos.deleted), len(guest_rows()), submits


def _step_fixture(names):
    @pytest.fixture(params=names)
    def fixture(request, guest_client, kratos, tokens, guest, resource):
        return Step(request.param, guest_client, kratos, tokens, guest, resource)

    return fixture


step = _step_fixture(STEPS)
v1_step = _step_fixture(V1_STEPS)
auth_step = _step_fixture(AUTH_STEPS)
rename_step = _step_fixture(["rename"])


def _assert_refusal_body(step, response, kind):
    """kind: failed(403) 또는 unavailable(503). /v1은 도메인 에러 JSON, /auth는 프록시 JSON"""
    assert response.status_code == {"failed": 403, "unavailable": 503}[kind], response.text
    if step.name in V1_STEPS:
        error_type = {"failed": "GuestVerificationFailedError", "unavailable": "GuestServiceUnavailableError"}[kind]
        assert response.json()["error_type"] == error_type
    else:
        assert response.json()["error"]["id"] == f"guest_verification_{kind}"


def _assert_refused(step, response, kind):
    _assert_refusal_body(step, response, kind)
    assert not step.reached(response)


def _is_verification_refusal(response) -> bool:
    if not response.content:
        return False
    body = response.json()
    if body.get("error_type") in ("GuestVerificationFailedError", "GuestServiceUnavailableError"):
        return True
    error = body.get("error")
    return isinstance(error, dict) and str(error.get("id", "")).startswith("guest_verification_")


# ============ 확인 결과 ============

def test_passed_token_reaches_the_step(step, turnstile):
    r = step.send()

    assert r.status_code in (200, 201, 204), r.text
    assert step.reached(r)
    [verification] = turnstile.requests
    assert parse_qs(verification.content.decode())["response"] == [WIDGET_TOKEN]


def test_secret_and_token_are_sent_as_form_fields_without_client_address(step, turnstile):
    step.send(headers={"CF-Connecting-IP": "203.0.113.7"})

    [request] = turnstile.requests
    assert str(request.url) == TURNSTILE_VERIFY
    assert request.method == "POST"
    assert request.headers["content-type"] == "application/x-www-form-urlencoded"
    assert parse_qs(request.content.decode()) == {"secret": [TURNSTILE_SECRET], "response": [WIDGET_TOKEN]}
    assert b"203.0.113.7" not in request.content
    assert b"testclient" not in request.content


@pytest.mark.parametrize("token", [None, "", "a" * 2049], ids=["missing", "empty", "too_long"])
def test_missing_empty_or_long_token_is_refused_without_verification(step, turnstile, token):
    r = step.send(token=token)

    _assert_refused(step, r, "failed")
    assert turnstile.requests == []


def test_token_of_max_length_is_verified(step, turnstile):
    r = step.send(token="a" * 2048)
    assert step.reached(r)
    assert len(turnstile.requests) == 1


def test_rejected_token_is_refused(step, turnstile):
    turnstile.success = False
    _assert_refused(step, step.send(), "failed")
    assert len(turnstile.requests) == 1


@pytest.mark.parametrize("failure", ["down", "status_500", "not_json", "no_success", "success_not_bool"])
def test_unverifiable_token_is_refused(step, turnstile, failure):
    if failure == "down":
        turnstile.down = True
    elif failure == "status_500":
        turnstile.status = 500
    elif failure == "not_json":
        turnstile.body = b"<html>"
    elif failure == "no_success":
        turnstile.body = b'{"error-codes": []}'
    else:
        turnstile.body = b'{"success": "true"}'

    _assert_refused(step, step.send(), "unavailable")


def test_v1_refusal_has_domain_error_body(v1_step, host, resource):
    refused = v1_step.send(token=None)
    host.statuses[resource] = GuestHostStatus.CLOSED
    domain_error = v1_step.client.post(
        LOOKUP, json={"resource_type": "meeting", "resource_id": str(resource), "name": "x"},
        headers={TOKEN_HEADER: WIDGET_TOKEN},
    )

    assert domain_error.json()["error_type"] == "GuestEntryRefusedError"
    assert refused.json().keys() == domain_error.json().keys()
    assert refused.json()["message"] == "확인을 통과하지 못했습니다. 다시 시도하세요"
    assert refused.json()["path"] == {"lookup": LOOKUP, "create": CREATE, "delete": ME}[v1_step.name]


def test_token_in_create_body_is_not_read(guest_client, turnstile, resource):
    body = {"resource_type": "meeting", "resource_id": str(resource), "name": "영희", "password": "1234"}
    r = guest_client.post(CREATE, json={**body, "turnstile_token": WIDGET_TOKEN})
    assert r.status_code == 403
    assert turnstile.requests == []
    assert guest_rows() == []


def test_token_header_is_not_forwarded_to_kratos(auth_step):
    auth_step.send()

    submits = [r for r in auth_step.kratos.public_requests if r.method != "GET"]
    assert submits
    assert all("x-turnstile-token" not in r.headers for r in submits)


# ============ 순서: 요청 한도 → Turnstile → 게스트 확인·Kratos ============

@pytest.fixture
def rate_limited(guest_client, monkeypatch):
    import app.core.config as app_config
    from app.ratelimit.limiter import reset_limiter
    from app.ratelimit.storage.memory import reset_storage

    monkeypatch.setattr(app_config.settings, "RATE_LIMIT_ENABLED", True)
    reset_storage()
    reset_limiter()
    yield
    reset_storage()
    reset_limiter()


def test_rate_limited_request_is_not_verified(rate_limited, step, turnstile):
    turnstile.success = False
    for _ in range(200):
        verified = len(turnstile.requests)
        r = step.send()
        if r.status_code == 429:
            break
        _assert_refused(step, r, "failed")
    assert r.status_code == 429
    assert len(turnstile.requests) == verified


@pytest.mark.parametrize("step_name", ["lookup", "create", "rename"])
def test_verification_comes_before_resource_and_name_checks(
        guest_client, kratos, tokens, guest, host, resource, turnstile, step_name
):
    """닫힌 리소스(이름 찾기), 이미 있는 이름(생성·이름 변경)이라도 토큰 거절이 먼저다"""
    make_guest(kratos, resource, name="영희")
    make_guest(kratos, resource, name="철수")
    if step_name == "lookup":
        host.statuses[resource] = GuestHostStatus.CLOSED
    step = Step(step_name, guest_client, kratos, tokens, guest, resource)
    turnstile.success = False

    r = step.send()

    assert r.status_code == 403
    if step_name == "rename":
        assert r.json()["error"]["id"] == "guest_verification_failed"
    else:
        assert r.json()["error_type"] == "GuestVerificationFailedError"


@pytest.mark.parametrize("step_name", ["create", "login", "rename"])
def test_verification_comes_before_guest_kratos_slot(
        guest_client, kratos, tokens, guest, resource, turnstile, monkeypatch, step_name
):
    monkeypatch.setattr(kratos_slots, "guest_slots", kratos_slots.Slots(0))
    monkeypatch.setattr(kratos_slots, "WAIT_SECONDS", 0.01)
    step = Step(step_name, guest_client, kratos, tokens, guest, resource)

    turnstile.success = False
    assert step.send().status_code == 403
    turnstile.success = True
    assert step.send().status_code == 429
    assert len(turnstile.requests) == 2


def test_checks_after_verification_still_apply(guest_client, kratos, host, turnstile, resource):
    make_guest(kratos, resource, name="영희")
    body = {"resource_type": "meeting", "resource_id": str(resource), "name": "영희", "password": "1234"}
    assert guest_client.post(CREATE, json=body, headers={TOKEN_HEADER: WIDGET_TOKEN}).status_code == 409

    closed = uuid.uuid4()
    host.statuses[closed] = GuestHostStatus.CLOSED
    r = guest_client.post(CREATE, json={**body, "resource_id": str(closed)}, headers={TOKEN_HEADER: WIDGET_TOKEN})
    assert r.json()["error_type"] == "GuestEntryRefusedError"

    assert len(turnstile.requests) == 2
    assert len(kratos.identities) == 1


# ============ 단계 판정: /v1 ============

@pytest.mark.parametrize("path", [f"{CREATE}/", f"{LOOKUP}/", f"{ME}/"])
def test_v1_path_with_trailing_slash_is_redirected_without_reaching_the_step(guest_client, kratos, turnstile, path):
    method = "DELETE" if path.startswith(ME) else "POST"
    r = guest_client.request(method, path, json={}, follow_redirects=False)
    assert r.status_code == 307
    assert turnstile.requests == []
    assert kratos.identities == {}


def test_percent_encoded_v1_path_needs_token(v1_step, turnstile):
    path = {"lookup": "/v1/guests/%6Cookup", "create": "/v1/guest%73", "delete": "/v1/guests/m%65"}[v1_step.name]
    _assert_refused(v1_step, v1_step.send(token=None, path=path), "failed")


@pytest.mark.parametrize("method", ["GET", "PUT", "PATCH"])
def test_other_methods_on_v1_step_paths_are_not_steps(v1_step, turnstile, method):
    r = v1_step.send(token=None, method=method)
    assert r.status_code == 405
    assert turnstile.requests == []
    assert not v1_step.reached(r)


# ============ 단계 판정: /auth 설정 제출 ============

@pytest.mark.parametrize(
    "path",
    [
        "/auth/self-service/settings/",
        "/auth/Self-Service/Settings",
        "/auth/self-service/settin%67s",
        "/auth/self-service/x/../settings",
    ],
)
def test_other_settings_path_spellings_need_token(rename_step, turnstile, path):
    _assert_refused(rename_step, rename_step.send(token=None, path=path), "failed")


@pytest.mark.parametrize("method", ["PUT", "PATCH"])
def test_other_submit_methods_need_token(auth_step, turnstile, method):
    _assert_refused(auth_step, auth_step.send(token=None, method=method), "failed")


def test_form_encoded_rename_needs_token(rename_step, turnstile):
    r = rename_step.client.post(
        f"{SETTINGS}?flow=f1",
        data={"method": "profile", "traits.handle": rename_step.handle, "traits.name": "철수"},
        headers={"X-Session-Token": rename_step.session},
    )
    _assert_refused(rename_step, r, "failed")


def test_guest_session_with_other_authorization_header_needs_token(rename_step, turnstile):
    r = rename_step.send(token=None, headers={"Authorization": "Bearer other-session"})
    _assert_refused(rename_step, r, "failed")


def test_guest_session_settings_submit_of_other_method_needs_token(rename_step, turnstile):
    """게스트 세션의 설정 제출은 method와 상관없이 게스트 단계다"""
    rename_step.kratos.authentication_methods = [{"method": "code_recovery"}]
    r = rename_step.client.post(
        f"{SETTINGS}?flow=f1",
        json={"method": "password", "password": "New-Pass-123"},
        headers={"X-Session-Token": rename_step.session},
    )
    _assert_refused(rename_step, r, "failed")


def test_member_settings_submit_needs_no_token(guest_client, kratos, turnstile):
    member = kratos.add_identity("default", {"email": "member@example.com"}, "member-pass")
    kratos.sessions["member-session"] = member["id"]
    kratos.authentication_methods = [{"method": "code_recovery"}]

    guest_client.post(
        f"{SETTINGS}?flow=f1",
        json={"method": "password", "password": "New-Pass-123"},
        headers={"X-Session-Token": "member-session"},
    )

    assert turnstile.requests == []
    assert any(sent.method == "POST" and sent.url.path == "/self-service/settings" for sent in kratos.public_requests)


# ============ 꺼진 상태, CORS ============

def test_flag_off_makes_no_verification(step, guest_off, turnstile):
    guest_off()
    r = step.send(token=None)

    if step.name in V1_STEPS:
        assert r.status_code == 404
    elif step.name == "login":
        assert r.status_code == 200
    else:
        assert r.json()["error"]["id"] == "settings_require_email_recovery"
    assert turnstile.requests == []


def test_refusal_carries_cors_headers(step, turnstile):
    r = step.send(token=None, headers={"Origin": "http://localhost:3000"})
    _assert_refused(step, r, "failed")
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_preflight_is_answered_without_verification(step, turnstile):
    path = {"lookup": LOOKUP, "create": CREATE, "delete": ME, "login": LOGIN, "rename": SETTINGS}[step.name]
    r = step.client.options(
        path,
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "DELETE" if step.name == "delete" else "POST",
            "Access-Control-Request-Headers": "content-type,x-turnstile-token",
        },
    )
    assert r.status_code == 200
    allowed = r.headers["access-control-allow-headers"].lower()
    assert "x-turnstile-token" in allowed or allowed == "*"
    assert turnstile.requests == []


# ============ 토큰은 한 번만 ============

def test_reused_token_is_refused_without_siteverify(step, strict_turnstile):
    assert step.send(token="once").status_code in (200, 201, 204)
    effects = step.effects()

    r = step.send(token="once")

    _assert_refusal_body(step, r, "failed")
    assert step.effects() == effects
    assert len(strict_turnstile.requests) == 1


@pytest.mark.parametrize(
    "first,second",
    [("lookup", "create"), ("create", "login"), ("login", "rename"), ("rename", "delete"), ("delete", "lookup")],
)
def test_token_used_for_one_step_is_refused_for_another(
        guest_client, kratos, tokens, guest, resource, strict_turnstile, first, second
):
    first_step = Step(first, guest_client, kratos, tokens, guest, resource)
    second_step = Step(second, guest_client, kratos, tokens, guest, resource)
    assert first_step.send(token="once").status_code in (200, 201, 204)
    effects = second_step.effects()

    r = second_step.send(token="once")

    _assert_refusal_body(second_step, r, "failed")
    assert second_step.effects() == effects
    assert len(strict_turnstile.requests) == 1


def test_token_that_failed_verification_stays_spent(step, strict_turnstile):
    strict_turnstile.success = False
    _assert_refused(step, step.send(token="once"), "failed")
    strict_turnstile.success = True

    _assert_refused(step, step.send(token="once"), "failed")
    assert len(strict_turnstile.requests) == 1


def test_token_sent_while_siteverify_is_unreachable_stays_spent(step, strict_turnstile):
    strict_turnstile.down = True
    _assert_refused(step, step.send(token="once"), "unavailable")
    strict_turnstile.down = False

    _assert_refused(step, step.send(token="once"), "failed")
    assert strict_turnstile.requests == []


def test_different_tokens_are_each_verified(step, strict_turnstile):
    step.send(token="first")
    step.send(token="second")
    assert len(strict_turnstile.requests) == 2


@pytest.mark.asyncio
async def test_concurrent_uses_of_one_token_reach_siteverify_once(strict_turnstile):
    results = await asyncio.gather(*[turnstile_client.verify("same") for _ in range(5)])

    assert sorted(results) == [False, False, False, False, True]
    assert len(strict_turnstile.requests) == 1


@pytest.mark.asyncio
async def test_concurrent_requests_with_one_token_pass_once(guest_client, kratos, guest, resource, strict_turnstile):
    from app.main import app

    body = {"resource_type": "meeting", "resource_id": str(resource), "name": "민수"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        responses = await asyncio.gather(
            *[client.post(LOOKUP, json=body, headers={TOKEN_HEADER: "once"}) for _ in range(5)]
        )

    assert sorted(r.status_code for r in responses) == [200, 403, 403, 403, 403]
    assert len(strict_turnstile.requests) == 1


@pytest.mark.parametrize("secret", sorted(turnstile_client.TESTING_SECRET_KEYS))
def test_testing_secret_key_skips_the_single_use_record(step, turnstile, monkeypatch, secret):
    """Cloudflare 테스트 키의 위젯은 늘 같은 더미 토큰을 준다"""
    monkeypatch.setattr(app_config.settings, "TURNSTILE_SECRET_KEY", secret)
    dummy = "XXXX.DUMMY.TOKEN.XXXX"

    assert step.send(token=dummy).status_code in (200, 201, 204)
    r = step.send(token=dummy)

    assert not _is_verification_refusal(r)
    assert len(turnstile.requests) == 2


def test_spent_token_is_kept_through_the_token_lifetime_then_forgotten(monkeypatch):
    """Turnstile 토큰은 300초 동안 유효하다"""
    now = [1000.0]
    monkeypatch.setattr(turnstile_client.time, "monotonic", lambda: now[0])
    spent = turnstile_client._SpentTokens()
    assert spent.claim("a")
    now[0] = 1000.0 + 300
    assert not spent.claim("a")
    now[0] = 1000.0 + turnstile_client.SPENT_TOKEN_TTL_SECONDS - 1
    assert not spent.claim("a")
    now[0] = 1000.0 + turnstile_client.SPENT_TOKEN_TTL_SECONDS + 1
    assert spent.claim("a")


def test_full_record_forgets_the_oldest_token(monkeypatch):
    monkeypatch.setattr(turnstile_client, "SPENT_TOKEN_MAX", 2)
    spent = turnstile_client._SpentTokens()
    assert spent.claim("a") and spent.claim("b") and spent.claim("c")

    assert not spent.claim("b")
    assert not spent.claim("c")
    assert spent.claim("a")
