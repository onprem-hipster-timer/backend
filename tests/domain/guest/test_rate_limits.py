"""게스트 생성·이름 찾기와 /auth 프록시 제출의 rate limit

- 게스트 이름 찾기·생성: 클라이언트 IP 단위 (app/ratelimit/config.py)
- /auth 제출 (app/middleware/guest_gate.py): 설정 밖은 IP 단위, 로그인·가입·인증·복구는 같은 IP의 같은 식별자 단위로도,
  설정은 세션의 identity 단위
"""
import uuid

import pytest

from app.middleware.guest_gate import _identifier_key
from app.domain.guest.host import GuestHostStatus
from tests.domain.guest.helpers import make_guest

CREATE = "/v1/guests"
LOOKUP = "/v1/guests/lookup"
TOKEN = {"X-Turnstile-Token": "t"}
LOGIN = "/auth/self-service/login"
SETTINGS_SUBMIT = "/auth/self-service/settings?flow=f1"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}


@pytest.fixture
def resource(host):
    resource_id = uuid.uuid4()
    host.statuses[resource_id] = GuestHostStatus.OPEN
    return resource_id


@pytest.fixture
def rate_limited(guest_client, monkeypatch):
    import app.core.config as app_config
    from app.ratelimit.limiter import reset_limiter
    from app.ratelimit.storage.memory import reset_storage

    monkeypatch.setattr(app_config.settings, "RATE_LIMIT_ENABLED", True)
    reset_storage()
    reset_limiter()
    yield guest_client
    reset_storage()
    reset_limiter()


def _body(resource, name="민수", password="1234") -> dict:
    return {
        "resource_type": "meeting",
        "resource_id": str(resource),
        "name": name,
        "password": password,
    }


def _login(client, path, identifier, password="1", headers=None):
    return client.post(
        f"{path}?flow={uuid.uuid4()}",
        json={"method": "password", "identifier": identifier, "password": password},
        headers=headers,
    )


def _submit(client, path, body=None, content=None, headers=None):
    url = f"{path}?flow={uuid.uuid4()}"
    if content is not None:
        return client.post(url, content=content, headers=headers)
    return client.post(url, json=body, headers=headers)


def _rename(client, kratos, guest, name):
    token = f"token-{guest.identity_id}"
    kratos.sessions[token] = guest.identity_id
    handle = kratos.identities[guest.identity_id]["traits"]["handle"]
    body = {"method": "profile", "traits": {"handle": handle, "name": name}}
    return client.post(SETTINGS_SUBMIT, json=body, headers={"X-Session-Token": token})


def _assert_limited_after(statuses, allowed):
    assert 429 not in statuses[:allowed], statuses
    assert statuses[allowed] == 429, statuses


# 프록시가 Kratos로 넘기는 로그인 제출 경로의 여러 표기
LOGIN_PATHS = [
    "/auth/self-service/login",
    "/auth/self-service/login/",
    "/auth/Self-Service/Login",
    "/auth/self-service/../self-service/login",
    "/auth/self-service/log%69n",
]


# ============ 로그인: 같은 IP의 같은 식별자 ============

@pytest.mark.parametrize("path", LOGIN_PATHS)
def test_login_submissions_with_one_identifier_are_limited_to_5_per_ip(rate_limited, path):
    statuses = [_login(rate_limited, path, "member@example.com", str(i)).status_code for i in range(6)]
    _assert_limited_after(statuses, 5)


def test_login_path_spellings_share_one_identifier_counter(rate_limited):
    statuses = [_login(rate_limited, path, "member@example.com").status_code for path in [*LOGIN_PATHS, LOGIN]]
    _assert_limited_after(statuses, 5)


def test_every_non_get_auth_path_shares_the_ip_counter(rate_limited):
    # //self-service/login은 Kratos에 /login으로 나가 로그인 제출이 아니다
    paths = ["/auth/self-service/login", "/auth//self-service/login", "/auth/self-service/registration", "/auth/unknown"]
    statuses = [_login(rate_limited, paths[i % len(paths)], f"member{i}@example.com").status_code for i in range(61)]
    _assert_limited_after(statuses, 60)


def test_identifier_spellings_share_one_counter(rate_limited):
    responses = [
        _login(rate_limited, LOGIN, "x@guest.invalid"),
        _login(rate_limited, LOGIN, "X@GUEST.INVALID"),
        _login(rate_limited, LOGIN, "  x@guest.invalid "),
        _login(rate_limited, LOGIN, "ｘ@guest.invalid"),  # 전각 x
        _submit(rate_limited, LOGIN, content="method=password&Identifier=x%40Guest.Invalid&password=1", headers=FORM),
        _submit(rate_limited, LOGIN, {"method": "password", "password_identifier": "x@guest.invalid", "password": "1"}),
    ]
    _assert_limited_after([r.status_code for r in responses], 5)


def test_unreadable_identifiers_share_one_counter(rate_limited):
    responses = [
        _submit(rate_limited, LOGIN, content='{"method":"password","identifier":"a@example.com",'
                                             '"Identifier":"b@example.com","password":"1"}',
                headers={"Content-Type": "application/json"}),
        _submit(rate_limited, LOGIN, content="identifier=a%40example.com&identifier=b%40example.com", headers=FORM),
        _submit(rate_limited, LOGIN, content='{"identifier":', headers={"Content-Type": "application/json"}),
        _submit(rate_limited, LOGIN, {"method": "password", "identifier": 123, "password": "1"}),
        _submit(rate_limited, LOGIN, {"method": "password", "identifier": ["a@example.com"], "password": "1"}),
        _submit(rate_limited, LOGIN, content=b"identifier=\xff", headers=FORM),
    ]
    _assert_limited_after([r.status_code for r in responses], 5)


def test_different_identifiers_from_one_ip_are_counted_separately_up_to_60(rate_limited):
    statuses = [
        _login(rate_limited, LOGIN, f"member{i}@example.com", str(j)).status_code
        for i in range(12)
        for j in range(5)
    ]
    assert 429 not in statuses
    assert _login(rate_limited, LOGIN, "member99@example.com").status_code == 429


def test_limited_response_tells_when_to_retry(rate_limited):
    for i in range(5):
        _login(rate_limited, LOGIN, "member@example.com", str(i))

    r = _login(rate_limited, LOGIN, "member@example.com")

    assert r.status_code == 429
    assert 0 < int(r.headers["Retry-After"]) <= 60
    assert r.json()["retry_after"] == int(r.headers["Retry-After"])


def test_identifier_key_does_not_contain_identifier():
    key = _identifier_key("ip:1.2.3.4", "/self-service/login", "member@example.com")
    assert "member" not in key and "example.com" not in key
    assert key.startswith("ip:1.2.3.4:")


# ============ 가입·인증·복구: 같은 IP의 같은 이메일 ============

@pytest.mark.parametrize(
    "path,body",
    [
        ("/auth/self-service/registration", {"method": "password", "traits": {"email": "new@example.com"}, "password": "pw"}),
        ("/auth/self-service/recovery", {"method": "code", "email": "member@example.com"}),
        ("/auth/self-service/verification", {"method": "code", "email": "member@example.com"}),
    ],
)
def test_address_submissions_with_one_email_are_limited_to_5_per_ip(rate_limited, path, body):
    statuses = [_submit(rate_limited, path, body).status_code for _ in range(6)]
    _assert_limited_after(statuses, 5)


def test_one_email_on_different_submit_paths_is_counted_separately(rate_limited):
    statuses = [_login(rate_limited, LOGIN, "member@example.com", str(i)).status_code for i in range(5)]
    statuses += [
        _submit(rate_limited, "/auth/self-service/recovery", {"method": "code", "email": "member@example.com"}).status_code
        for _ in range(5)
    ]
    assert 429 not in statuses


def test_submissions_without_identifier_are_counted_per_ip_only(rate_limited):
    statuses = [
        _submit(rate_limited, "/auth/self-service/registration", {"method": "oidc", "provider": "google"}).status_code
        for _ in range(10)
    ]
    assert 429 not in statuses


# ============ 설정: 세션의 identity ============

def test_settings_submits_are_counted_per_identity_not_per_ip(rate_limited, kratos, resource):
    first = make_guest(kratos, resource, name="민수")
    second = make_guest(kratos, resource, name="철수")
    for i in range(60):
        _login(rate_limited, LOGIN, f"member{i}@example.com")
    assert _login(rate_limited, LOGIN, "member99@example.com").status_code == 429  # IP 한도를 다 썼다

    statuses = [_rename(rate_limited, kratos, first, f"민수{i}").status_code for i in range(11)]

    assert statuses[:10] == [200] * 10, statuses
    assert statuses[10] == 429
    assert _rename(rate_limited, kratos, second, "영희").status_code == 200


def test_rejected_settings_submits_are_not_counted(rate_limited, kratos, resource):
    guest = make_guest(kratos, resource, name="민수")
    rejected = [
        rate_limited.post(SETTINGS_SUBMIT, json={"method": "profile", "traits": {"name": "x"}}).status_code
        for _ in range(70)
    ]
    assert set(rejected) == {403}
    assert _rename(rate_limited, kratos, guest, "철수").status_code == 200


# ============ GET, 게스트 이름 찾기·생성 ============

def test_get_requests_under_auth_are_not_limited(rate_limited):
    statuses = [rate_limited.get("/auth/self-service/login/api").status_code for _ in range(70)]
    statuses += [rate_limited.get("/auth/sessions/whoami").status_code for _ in range(70)]
    assert 429 not in statuses


def test_lookup_and_create_are_limited_per_ip_separately(rate_limited, resource):
    for _ in range(100):
        assert rate_limited.post(LOOKUP, json=_body(resource)).status_code == 200
    assert rate_limited.post(LOOKUP, json=_body(resource)).status_code == 429

    for i in range(100):
        assert rate_limited.post(CREATE, json=_body(resource, name=f"g{i}"), headers=TOKEN).status_code == 201
    assert rate_limited.post(CREATE, json=_body(resource, name="g100"), headers=TOKEN).status_code == 429


@pytest.mark.parametrize("path,limit", [(CREATE, 100), (LOOKUP, 100), (LOGIN, 60)])
def test_requests_with_different_tokens_from_one_ip_share_one_counter(rate_limited, tokens, resource, path, limit):
    statuses = []
    for i in range(limit + 1):
        headers = tokens.member(f"member-{i}")
        if path == CREATE:
            r = rate_limited.post(CREATE, json=_body(resource, name=f"g{i}"), headers={**headers, **TOKEN})
        elif path == LOOKUP:
            r = rate_limited.post(LOOKUP, json=_body(resource), headers=headers)
        else:
            r = _login(rate_limited, path, f"member{i}@example.com", headers=headers)
        statuses.append(r.status_code)

    _assert_limited_after(statuses, limit)


def test_other_routes_still_count_per_token(rate_limited, tokens):
    """per_ip가 아닌 규칙은 토큰의 sub로 센다 (/v1/friends/requests: 분당 20회)"""
    first, second = tokens.member("member-a"), tokens.member("member-b")
    body = {"friend_code": "NOPE0000"}
    a = [rate_limited.post("/v1/friends/requests", json=body, headers=first).status_code for _ in range(20)]
    b = rate_limited.post("/v1/friends/requests", json=body, headers=second).status_code
    assert 429 not in a
    assert b != 429
    assert rate_limited.post("/v1/friends/requests", json=body, headers=first).status_code == 429
