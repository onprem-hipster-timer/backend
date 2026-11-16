"""게스트 handle 로그인 제출의 Turnstile 확인 (/auth 프록시, GUEST_ENABLED=true)

로그인 제출의 식별자가 게스트 handle 주소면 X-Turnstile-Token 헤더의 토큰이 통과해야 Kratos에 넘긴다.
"""
import json
import uuid

import httpx
import pytest

from app.domain.guest.host import GuestHostStatus
from tests.domain.guest.helpers import make_guest

TOKEN_HEADER = "X-Turnstile-Token"


@pytest.fixture
def resource(host):
    resource_id = uuid.uuid4()
    host.statuses[resource_id] = GuestHostStatus.OPEN
    return resource_id


@pytest.fixture
def guest(kratos, resource):
    return make_guest(kratos, resource, name="민수", password="1234")


def _handle(kratos, guest) -> str:
    return kratos.identities[guest.identity_id]["traits"]["handle"]


def _login(client, body=None, token="token-from-widget", form=None, path="/auth/self-service/login"):
    headers = {TOKEN_HEADER: token} if token is not None else {}
    url = f"{path}?flow={uuid.uuid4()}"
    if form is not None:
        return client.post(url, data=form, headers=headers)
    return client.post(url, json=body, headers=headers)


def _password(identifier, password="1234", **extra) -> dict:
    return {"method": "password", "identifier": identifier, "password": password, **extra}


def _login_submits(kratos) -> list:
    return [r for r in kratos.public_requests if r.url.path.rstrip("/").lower() == "/self-service/login"]


# ============ 토큰 확인 ============

def test_guest_login_with_passed_token_is_forwarded(guest_client, kratos, turnstile, guest):
    r = _login(guest_client, _password(_handle(kratos, guest)))
    assert r.status_code == 200
    assert r.json()["session_token"]
    [verification] = turnstile.requests
    assert b"response=token-from-widget" in verification.content


def test_token_header_is_not_forwarded_to_kratos(guest_client, kratos, guest, monkeypatch):
    seen = []
    public = kratos.public

    async def recording(request):
        seen.append(request)
        return await public(request)

    kratos.public = recording
    _login(guest_client, _password(_handle(kratos, guest)))

    [submit] = [r for r in seen if r.url.path == "/self-service/login"]
    assert "x-turnstile-token" not in submit.headers


@pytest.mark.parametrize("token", [None, "", "a" * 2049], ids=["missing", "empty", "too_long"])
def test_guest_login_without_usable_token_is_403(guest_client, kratos, turnstile, guest, token):
    r = _login(guest_client, _password(_handle(kratos, guest)), token=token)

    assert r.status_code == 403
    assert r.json() == {
        "error": {
            "id": "guest_verification_failed",
            "code": 403,
            "status": "Forbidden",
            "reason": "확인을 통과하지 못했습니다. 다시 시도하세요.",
        }
    }
    assert turnstile.requests == []
    assert kratos.sessions == {}


def test_token_of_max_length_is_checked(guest_client, kratos, turnstile, guest):
    assert _login(guest_client, _password(_handle(kratos, guest)), token="a" * 2048).status_code == 200
    assert len(turnstile.requests) == 1


def test_rejected_token_is_403_and_not_forwarded(guest_client, kratos, turnstile, guest):
    turnstile.success = False
    r = _login(guest_client, _password(_handle(kratos, guest)))
    assert r.status_code == 403
    assert r.json()["error"]["id"] == "guest_verification_failed"
    assert kratos.sessions == {}


@pytest.mark.parametrize("failure", ["down", "status_500", "not_json"])
def test_unverifiable_token_is_503_and_not_forwarded(guest_client, kratos, turnstile, guest, failure):
    if failure == "down":
        turnstile.down = True
    elif failure == "status_500":
        turnstile.status = 500
    else:
        turnstile.body = b"<html>"

    r = _login(guest_client, _password(_handle(kratos, guest)))

    assert r.status_code == 503
    assert r.json() == {
        "error": {
            "id": "guest_verification_unavailable",
            "code": 503,
            "status": "Service Unavailable",
            "reason": "확인 서비스에 연결할 수 없습니다.",
        }
    }
    assert kratos.sessions == {}


def test_each_login_attempt_is_verified(guest_client, kratos, turnstile, guest):
    for _ in range(3):
        _login(guest_client, _password(_handle(kratos, guest)))
    assert len(turnstile.requests) == 3


def test_wrong_password_with_passed_token_gets_kratos_answer(guest_client, kratos, turnstile, guest):
    r = _login(guest_client, _password(_handle(kratos, guest), password="4321"))
    assert r.status_code == 400
    assert r.json()["ui"]["messages"][0]["id"] == 4000006
    assert len(turnstile.requests) == 1


# ============ 게스트 handle 판정 ============

@pytest.mark.parametrize(
    "transform",
    [
        lambda h: h.upper(),
        lambda h: h.replace("guest.invalid", "Guest.INVALID"),
        lambda h: f"  {h}  ",
        lambda h: f"\t{h.upper()}\n",
        lambda h: f"\v\f\r {h} \r\f\v",
    ],
    ids=["upper", "mixed_case_domain", "spaces", "tab_newline_upper", "other_ascii_spaces"],
)
def test_other_spellings_of_guest_handle_need_token(guest_client, kratos, turnstile, guest, transform):
    r = _login(guest_client, _password(transform(_handle(kratos, guest))), token=None)
    assert r.status_code == 403
    assert r.json()["error"]["id"] == "guest_verification_failed"


@pytest.mark.parametrize(
    "transform",
    [
        lambda h: h.replace("guest.invalid", "ｇｕｅｓｔ．ｉｎｖａｌｉｄ"),
        lambda h: h.replace("@", "＠"),
        lambda h: h.replace("invalid", "\u0130nvalid"),
        lambda h: h.replace("invalid", "inval\u0130d"),
        lambda h: f"\u00a0{h}\u3000",
    ],
    ids=["fullwidth_domain", "fullwidth_at", "dotted_capital_i", "dotted_capital_i_last", "unicode_spaces"],
)
def test_non_ascii_spellings_of_guest_handle_are_refused_without_verification(guest_client, kratos, turnstile, guest,
                                                                              transform):
    r = _login(guest_client, _password(transform(_handle(kratos, guest))))

    assert r.status_code == 400
    assert r.json()["error"]["id"] == "invalid_identifier"
    assert turnstile.requests == []
    assert _login_submits(kratos) == []
    assert kratos.sessions == {}


@pytest.mark.parametrize("key", ["identifier", "Identifier", "password_identifier", "PASSWORD_IDENTIFIER"])
def test_identifier_keys_are_read_ignoring_case(guest_client, kratos, guest, key):
    body = {"method": "password", key: _handle(kratos, guest), "password": "1234"}
    assert _login(guest_client, body, token=None).status_code == 403


@pytest.mark.parametrize("key", ["pa\u017f\u017fword_identifier", "PA\u017fSWORD_IDENTIFIER"])
def test_identifier_keys_are_read_with_unicode_case_folding(guest_client, kratos, guest, key):
    """JSON 키는 casefold로 비교한다 (U+017F는 s와 같다). Kratos가 식별자로 읽는 키보다 많은 표기를 식별자로 본다"""
    body = {"method": "password", key: _handle(kratos, guest), "password": "1234"}
    r = _login(guest_client, body, token=None)
    assert r.status_code == 403
    assert r.json()["error"]["id"] == "guest_verification_failed"


def test_identifier_and_folded_identifier_key_together_are_400(guest_client, kratos, turnstile, guest):
    body = {"method": "password", "identifier": "member@example.com", "pa\u017f\u017fword_identifier": _handle(kratos, guest)}
    r = _login(guest_client, body, token=None)
    assert r.status_code == 400
    assert r.json()["error"]["id"] == "invalid_request_body"
    assert turnstile.requests == []


@pytest.mark.parametrize("key", ["identifier", "password_identifier"])
def test_form_body_identifier_is_read(guest_client, kratos, guest, key):
    form = {"method": "password", key: _handle(kratos, guest), "password": "1234"}
    assert _login(guest_client, form=form, token=None).status_code == 403


@pytest.mark.parametrize("method", ["code", "oidc", "passkey", None])
def test_guest_identifier_with_other_method_needs_token(guest_client, kratos, turnstile, guest, method):
    body = {"identifier": _handle(kratos, guest)}
    if method is not None:
        body["method"] = method
    assert _login(guest_client, body, token=None).status_code == 403


@pytest.mark.parametrize(
    "identifier",
    ["member@example.com", "x@guest.invalid.example.com", "x@notguest.invalid", "guest.invalid", None, 3],
)
def test_other_identifiers_need_no_token_and_make_no_verification(guest_client, kratos, turnstile, identifier):
    body = {"method": "password", "password": "1234"}
    if identifier is not None:
        body["identifier"] = identifier
    r = _login(guest_client, body, token=None)
    assert r.status_code != 403
    assert turnstile.requests == []


def test_member_login_makes_no_verification(guest_client, kratos, turnstile):
    kratos.add_identity("default", {"email": "member@example.com"}, "member-pass")
    r = _login(guest_client, _password("member@example.com", password="member-pass"), token=None)
    assert r.status_code == 200
    assert turnstile.requests == []


# ============ 읽을 수 없는 본문 ============

@pytest.mark.parametrize(
    "content,content_type",
    [
        (b'{"identifier": "a@example.com", "Identifier": "x@guest.invalid"}', "application/json"),
        (b'{"identifier": "a@example.com", "password_identifier": "x@guest.invalid"}', "application/json"),
        (b"identifier=a%40example.com&identifier=x%40guest.invalid", "application/x-www-form-urlencoded"),
        (b"identifier=a%40example.com&password_identifier=x%40guest.invalid", "application/x-www-form-urlencoded"),
        (b"not json", "application/json"),
        (b"\xff\xfe", "application/x-www-form-urlencoded"),
    ],
    ids=["json_case_duplicate", "json_two_keys", "form_repeated", "form_two_keys", "json_broken", "form_not_utf8"],
)
def test_more_than_one_identifier_or_unreadable_body_is_400(guest_client, kratos, turnstile, content, content_type):
    r = guest_client.post(
        f"/auth/self-service/login?flow={uuid.uuid4()}",
        content=content,
        headers={"content-type": content_type, TOKEN_HEADER: "t"},
    )
    assert r.status_code == 400
    assert r.json()["error"]["id"] == "invalid_request_body"
    assert turnstile.requests == []
    assert kratos.sessions == {}


def test_guest_handle_in_query_is_refused(guest_client, kratos, turnstile, guest):
    r = guest_client.post(
        f"/auth/self-service/login?flow=f1&identifier={_handle(kratos, guest)}",
        json={"method": "password", "password": "1234"},
    )
    assert r.status_code == 400
    assert r.json()["error"]["id"] == "invalid_request_body"
    assert turnstile.requests == []


def test_login_get_with_values_in_query_is_refused(guest_client, kratos, turnstile, guest):
    r = guest_client.get(
        f"/auth/self-service/login?flow=f1&method=password&identifier={_handle(kratos, guest)}&password=1234",
        headers={TOKEN_HEADER: "token-from-widget"},
    )
    assert r.status_code == 400
    assert r.json()["error"]["id"] == "invalid_request_body"
    assert kratos.public_requests == []
    assert turnstile.requests == []
    assert kratos.sessions == {}


@pytest.mark.parametrize(
    "path",
    [
        "/auth/self-service/login/",
        "/auth/self-service/login//",
        "/auth/Self-Service/Login",
        "/auth/self-service/log%69n",
        "/auth/self-service/./login",
        "/auth/self-service/x/../login",
    ],
)
def test_other_login_path_spellings_need_token(guest_client, kratos, guest, path):
    r = _login(guest_client, _password(_handle(kratos, guest)), token=None, path=path)
    assert r.status_code == 403
    assert r.json()["error"]["id"] == "guest_verification_failed"
    assert kratos.sessions == {}


@pytest.mark.parametrize(
    "path",
    [
        "/auth//self-service/login",
        "/auth/self-service//login",
        "/auth/%2e/self-service/login",
        "/auth/./self-service/login",
        "/auth/x/%2e%2e/self-service/login",
        "/auth/self-service/login%2f",
        "/auth/self-service%2flogin",
        "/auth/self-service/login/.",
        "/auth/self-service/LOGIN/",
        "/auth/self-service/login;x=1",
        "/auth/self-service/login/..;/login",
        "/auth/self-service/login%20",
        "/auth/self-service\\login",
        "/auth/self-service/login%3fflow=1",
        "/auth/self-service/login%23",
    ],
)
def test_unusual_login_path_spellings_do_not_reach_kratos_login_without_token(
        guest_client, kratos, turnstile, guest, path
):
    _login(guest_client, _password(_handle(kratos, guest)), token=None, path=path)

    assert _login_submits(kratos) == []
    assert kratos.sessions == {}
    assert turnstile.requests == []


@pytest.mark.parametrize(
    "content_type",
    [
        "application/json; charset=utf-8",
        "Application/JSON",
        "text/plain",
        None,
        "application/x-www-form-urlencoded, application/json",
        "application/json, application/x-www-form-urlencoded",
        "multipart/form-data; boundary=x",
        "application/octet-stream",
    ],
)
def test_json_guest_login_under_other_content_types_does_not_reach_kratos(guest_client, kratos, turnstile, guest,
                                                                         content_type):
    headers = {} if content_type is None else {"content-type": content_type}
    content = json.dumps(_password(_handle(kratos, guest))).encode()

    r = guest_client.post(f"/auth/self-service/login?flow={uuid.uuid4()}", content=content, headers=headers)

    assert r.json()["error"]["id"] in ("guest_verification_failed", "invalid_request_body")
    assert _login_submits(kratos) == []
    assert kratos.sessions == {}


@pytest.mark.parametrize(
    "content_type",
    [
        "application/x-www-form-urlencoded; charset=UTF-8",
        "APPLICATION/X-WWW-FORM-URLENCODED",
        " application/x-www-form-urlencoded ",
        "application/x-www-form-urlencoded, text/plain",
        "text/plain, application/x-www-form-urlencoded",
        "multipart/form-data; boundary=x",
    ],
)
def test_form_guest_login_under_other_content_types_does_not_reach_kratos(guest_client, kratos, turnstile, guest,
                                                                         content_type):
    handle = _handle(kratos, guest).replace("@", "%40")
    content = f"method=password&identifier={handle}&password=1234".encode()

    r = guest_client.post(
        f"/auth/self-service/login?flow={uuid.uuid4()}", content=content, headers={"content-type": content_type}
    )

    assert r.json()["error"]["id"] in ("guest_verification_failed", "invalid_request_body")
    assert _login_submits(kratos) == []
    assert kratos.sessions == {}


@pytest.mark.asyncio
async def test_chunked_guest_login_needs_token(guest_client, kratos, turnstile, guest):
    from app.main import app

    content = json.dumps(_password(_handle(kratos, guest))).encode()

    async def chunks():
        yield content[:10]
        yield content[10:]

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            f"/auth/self-service/login?flow={uuid.uuid4()}", content=chunks(), headers={"content-type": "application/json"}
        )

    assert r.status_code == 403
    assert r.json()["error"]["id"] == "guest_verification_failed"
    assert _login_submits(kratos) == []


# ============ 꺼진 상태, rate limit, CORS ============

def test_flag_off_needs_no_token_and_makes_no_verification(guest_client, guest_off, kratos, turnstile, guest):
    handle = _handle(kratos, guest)
    guest_off()
    r = _login(guest_client, _password(handle), token=None)
    assert r.status_code == 200
    assert turnstile.requests == []


def test_flag_off_keeps_identifier_body_rules_as_before(guest_client, guest_off, turnstile):
    """꺼져 있으면 식별자를 읽지 않는다 (식별자가 둘이어도 이 검사로는 거절하지 않는다)"""
    guest_off()
    r = guest_client.post(
        f"/auth/self-service/login?flow={uuid.uuid4()}",
        json={"method": "password", "identifier": "a@example.com", "password_identifier": "x@guest.invalid"},
    )
    # 프록시가 거절하지 않고 넘겨 Kratos(가짜)가 답한다
    assert "error" not in r.json()
    assert "ui" in r.json()
    assert turnstile.requests == []


def test_rate_limit_applies_before_verification(guest_client, kratos, turnstile, guest, monkeypatch):
    import app.core.config as app_config
    from app.ratelimit.limiter import reset_limiter
    from app.ratelimit.storage.memory import reset_storage

    monkeypatch.setattr(app_config.settings, "RATE_LIMIT_ENABLED", True)
    reset_storage()
    reset_limiter()
    try:
        statuses = [_login(guest_client, _password(_handle(kratos, guest), password=str(i))).status_code for i in range(6)]
    finally:
        reset_storage()
        reset_limiter()

    assert 429 not in statuses[:5]
    assert statuses[5] == 429
    assert len(turnstile.requests) == 5


def test_browser_preflight_allows_turnstile_header(guest_client):
    r = guest_client.options(
        "/auth/self-service/login",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-turnstile-token",
        },
    )
    assert r.status_code == 200
    allowed = r.headers["access-control-allow-headers"].lower()
    assert "x-turnstile-token" in allowed or allowed == "*"
