"""게스트 생성·이름 찾기와 /auth 프록시 제출의 rate limit (클라이언트 IP 단위)"""
import uuid

import pytest

from app.domain.guest.host import GuestHostStatus

CREATE = "/v1/guests"
LOOKUP = "/v1/guests/lookup"


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
        "turnstile_token": "t",
    }


def _login(client, path, identifier, password, headers=None):
    return client.post(
        f"{path}?flow={uuid.uuid4()}",
        json={"method": "password", "identifier": identifier, "password": password},
        headers=headers,
    )


# 프록시가 Kratos로 넘기는 로그인 제출 경로의 여러 표기
LOGIN_PATHS = [
    "/auth/self-service/login",
    "/auth/self-service/login/",
    "/auth//self-service/login",
    "/auth/Self-Service/Login",
    "/auth/self-service/../self-service/login",
    "/auth/self-service/log%69n",
]


@pytest.mark.parametrize("path", LOGIN_PATHS)
def test_login_submissions_are_limited_to_10_per_ip(rate_limited, resource, path):
    assert rate_limited.post(CREATE, json=_body(resource)).status_code == 201
    handle = rate_limited.post(LOOKUP, json=_body(resource)).json()["handle"]

    statuses = [_login(rate_limited, path, handle, str(i)).status_code for i in range(11)]

    assert 429 not in statuses[:10], statuses
    assert statuses[10] == 429


def test_login_path_spellings_share_one_counter(rate_limited, resource):
    statuses = [_login(rate_limited, path, "x@guest.invalid", "1").status_code for path in LOGIN_PATHS * 2]
    assert statuses[:10].count(429) == 0
    assert statuses[10:] == [429, 429]


def test_get_requests_under_auth_are_not_limited(rate_limited):
    statuses = [rate_limited.get("/auth/self-service/login/api").status_code for _ in range(15)]
    statuses += [rate_limited.get("/auth/sessions/whoami").status_code for _ in range(15)]
    assert 429 not in statuses


def test_lookup_and_create_are_limited_per_ip_separately(rate_limited, resource):
    for _ in range(10):
        assert rate_limited.post(LOOKUP, json=_body(resource)).status_code == 200
    assert rate_limited.post(LOOKUP, json=_body(resource)).status_code == 429

    for i in range(10):
        assert rate_limited.post(CREATE, json=_body(resource, name=f"g{i}")).status_code == 201
    assert rate_limited.post(CREATE, json=_body(resource, name="g10")).status_code == 429


@pytest.mark.parametrize("path", [CREATE, LOOKUP, "/auth/self-service/login"])
def test_requests_with_different_tokens_from_one_ip_share_one_counter(rate_limited, tokens, resource, path):
    statuses = []
    for i in range(11):
        headers = tokens.member(f"member-{i}")
        if path == CREATE:
            r = rate_limited.post(CREATE, json=_body(resource, name=f"g{i}"), headers=headers)
        elif path == LOOKUP:
            r = rate_limited.post(LOOKUP, json=_body(resource), headers=headers)
        else:
            r = _login(rate_limited, path, "x@guest.invalid", "1", headers=headers)
        statuses.append(r.status_code)

    assert 429 not in statuses[:10], statuses
    assert statuses[10] == 429


def test_other_routes_still_count_per_token(rate_limited, tokens):
    """per_ip가 아닌 규칙은 토큰의 sub로 센다 (/v1/friends/requests: 분당 20회)"""
    first, second = tokens.member("member-a"), tokens.member("member-b")
    body = {"friend_code": "NOPE0000"}
    a = [rate_limited.post("/v1/friends/requests", json=body, headers=first).status_code for _ in range(20)]
    b = rate_limited.post("/v1/friends/requests", json=body, headers=second).status_code
    assert 429 not in a
    assert b != 429
    assert rate_limited.post("/v1/friends/requests", json=body, headers=first).status_code == 429
