"""
회원의 사용성 분석 동의 E2E 테스트

- GET /v1/users/me의 analytics_consent(granted·denied·null)와 analytics_consent_updated_at
- PUT /v1/users/me/analytics-consent로 granted·denied를 정한다
- 약관 동의(consent_required)와 따로다
게스트 토큰·토큰 없는 요청: tests/domain/guest/test_analytics_consent_member_only.py
계정 파기: tests/test_account_purge_e2e.py
"""
from datetime import datetime, timedelta

import pytest

import app.core.config as app_config
from app.db.session import _session_manager
from app.models.user_profile import UserProfile

ANALYTICS = "/v1/users/me/analytics-consent"


def _set(client, value):
    return client.put(ANALYTICS, json={"analytics_consent": value})


def _when(profile: dict) -> datetime:
    return datetime.strptime(profile["analytics_consent_updated_at"], "%Y-%m-%dT%H:%M:%S%z")


def _age_choice(sub: str, age: timedelta) -> None:
    """저장된 선택 시각을 age만큼 앞당긴다 (시각이 바뀌는지 초 단위로 가리려고)"""
    with _session_manager.get_session() as session:
        profile = session.get(UserProfile, sub)
        profile.analytics_consent_updated_at -= age
        session.add(profile)
        session.commit()


def test_not_chosen_by_default(e2e_client):
    profile = e2e_client.get("/v1/users/me").json()

    assert profile["analytics_consent"] is None
    assert profile["analytics_consent_updated_at"] is None


@pytest.mark.parametrize("value", ["granted", "denied"])
def test_set_and_read_back(e2e_client, value):
    before = datetime.now().astimezone().replace(microsecond=0)

    r = _set(e2e_client, value)

    assert r.status_code == 200, r.text
    assert r.json()["analytics_consent"] == value
    assert _when(r.json()) >= before
    profile = e2e_client.get("/v1/users/me").json()
    assert profile["analytics_consent"] == value
    assert profile["analytics_consent_updated_at"] == r.json()["analytics_consent_updated_at"]
    assert profile["id"] == "test-user-id"


def test_response_is_the_profile(e2e_client):
    r = _set(e2e_client, "granted")

    assert r.json() == e2e_client.get("/v1/users/me").json()


@pytest.mark.parametrize("first, second", [("granted", "denied"), ("denied", "granted")])
def test_change_updates_value_and_time(e2e_client, first, second):
    _set(e2e_client, first)
    _age_choice("test-user-id", timedelta(hours=1))
    earlier = _when(e2e_client.get("/v1/users/me").json())

    r = _set(e2e_client, second)

    assert r.status_code == 200, r.text
    assert r.json()["analytics_consent"] == second
    assert _when(r.json()) > earlier


@pytest.mark.parametrize("value", ["granted", "denied"])
def test_same_value_again_keeps_time(e2e_client, value):
    _set(e2e_client, value)
    _age_choice("test-user-id", timedelta(hours=1))
    stored = e2e_client.get("/v1/users/me").json()

    r = _set(e2e_client, value)

    assert r.status_code == 200, r.text
    assert r.json()["analytics_consent"] == value
    assert r.json()["analytics_consent_updated_at"] == stored["analytics_consent_updated_at"]


@pytest.mark.parametrize(
    "body",
    [
        {"analytics_consent": None},
        {"analytics_consent": "GRANTED"},
        {"analytics_consent": "Granted"},
        {"analytics_consent": "yes"},
        {"analytics_consent": ""},
        {"analytics_consent": True},
        {"analytics_consent": 1},
        {"analytics_consent": ["granted"]},
        {},
        {"granted": True},
        None,
    ],
    ids=["null", "upper", "title", "yes", "empty", "true", "one", "list", "no_field", "other_field", "no_body"],
)
def test_invalid_body_is_422_and_keeps_stored(e2e_client, body):
    _set(e2e_client, "denied")
    stored = e2e_client.get("/v1/users/me").json()

    r = e2e_client.put(ANALYTICS, json=body)

    assert r.status_code == 422, r.text
    assert e2e_client.get("/v1/users/me").json() == stored


def test_invalid_body_on_new_profile_leaves_not_chosen(e2e_client):
    assert _set(e2e_client, "maybe").status_code == 422

    assert e2e_client.get("/v1/users/me").json()["analytics_consent"] is None


def test_each_member_has_own_choice(multi_user_e2e):
    a = multi_user_e2e.as_user("user-a")
    b = multi_user_e2e.as_user("user-b")

    assert _set(a, "granted").status_code == 200
    assert b.get("/v1/users/me").json()["analytics_consent"] is None

    assert _set(b, "denied").status_code == 200
    assert a.get("/v1/users/me").json()["analytics_consent"] == "granted"
    assert b.get("/v1/users/me").json()["analytics_consent"] == "denied"


def test_other_profiles_are_not_readable_or_writable_by_path(multi_user_e2e):
    a = multi_user_e2e.as_user("user-a")
    b = multi_user_e2e.as_user("user-b")
    _set(a, "granted")

    assert b.get("/v1/users/user-a").status_code in (404, 405)
    assert b.put("/v1/users/user-a/analytics-consent", json={"analytics_consent": "denied"}).status_code in (404, 405)
    assert a.get("/v1/users/me").json()["analytics_consent"] == "granted"


# ============ 약관 동의와 따로다 ============

@pytest.fixture
def enforced(monkeypatch):
    monkeypatch.setattr(app_config.settings, "CONSENT_ENFORCED", True)


def test_member_without_required_consent_can_set_it(multi_user_e2e, enforced):
    a = multi_user_e2e.as_user("user-a")

    r = _set(a, "granted")

    assert r.status_code == 200, r.text
    assert r.json()["analytics_consent"] == "granted"
    assert r.json()["consent_required"] is True
    blocked = a.get("/v1/todos")
    assert blocked.status_code == 428
    assert blocked.json()["message"] == "consent_required"


def test_it_does_not_change_required_consent(multi_user_e2e, enforced):
    a = multi_user_e2e.as_user("user-a")
    version = a.get("/v1/users/me").json()["consent_version"]
    assert a.put(
        "/v1/users/me/consent",
        json={"version": version, "age_over_14": True, "terms": True, "privacy": True},
    ).status_code == 200

    for value in ("denied", "granted"):
        r = _set(a, value)
        assert r.status_code == 200, r.text
        assert r.json()["consent_required"] is False
        assert a.get("/v1/todos").status_code == 200


# ============ 휴면 계정 ============

def test_dormant_member_gets_423_and_keeps_choice(multi_user_e2e):
    a = multi_user_e2e.as_user("user-a")
    _set(a, "granted")
    assert a.post("/v1/users/me/deletion").status_code == 200

    r = _set(a, "denied")

    assert r.status_code == 423
    assert r.json()["message"] == "account_deletion_pending"
    assert a.get("/v1/users/me").json()["analytics_consent"] == "granted"
