"""현재 약관 버전에 동의하지 않은 사용자의 요청 제한

동의가 필요한 사용자는 프로필 조회와 동의 기록 외의 인증 요청이 428(`consent_required`)이다.
"""
import pytest

import app.core.config as app_config

SCHEDULES = ("/v1/schedules", {"start_date": "2024-01-01T00:00:00Z", "end_date": "2024-01-01T23:59:59Z"})


@pytest.fixture
def enforced(monkeypatch):
    monkeypatch.setattr(app_config.settings, "CONSENT_ENFORCED", True)


def _agree(client):
    version = client.get("/v1/users/me").json()["consent_version"]
    r = client.put(
        "/v1/users/me/consent",
        json={"version": version, "age_over_14": True, "terms": True, "privacy": True},
    )
    assert r.status_code == 200, r.text


def _schedules(client):
    path, params = SCHEDULES
    return client.get(path, params=params)


def test_enforced_by_default():
    assert app_config.Settings(_env_file=None, CONSENT_ENFORCED=True).CONSENT_ENFORCED is True
    import os
    saved = os.environ.pop("CONSENT_ENFORCED", None)
    try:
        assert app_config.Settings(_env_file=None).CONSENT_ENFORCED is True
    finally:
        if saved is not None:
            os.environ["CONSENT_ENFORCED"] = saved


def test_other_requests_are_forbidden_until_consent(multi_user_e2e, enforced):
    a = multi_user_e2e.as_user("user-a")

    r = _schedules(a)
    assert r.status_code == 428
    assert r.json()["message"] == "consent_required"

    _agree(a)
    assert _schedules(a).status_code == 200


def test_profile_and_consent_are_allowed(multi_user_e2e, enforced):
    a = multi_user_e2e.as_user("user-a")

    profile = a.get("/v1/users/me")
    assert profile.status_code == 200
    assert profile.json()["consent_required"] is True
    _agree(a)


def test_new_version_forbids_again(multi_user_e2e, enforced, monkeypatch):
    a = multi_user_e2e.as_user("user-a")
    _agree(a)
    monkeypatch.setattr(app_config.settings, "CONSENT_VERSION", "2099-01-01")

    r = _schedules(a)
    assert r.status_code == 428
    assert r.json()["message"] == "consent_required"

    _agree(a)
    assert _schedules(a).status_code == 200


def test_consent_is_per_user(multi_user_e2e, enforced):
    a = multi_user_e2e.as_user("user-a")
    b = multi_user_e2e.as_user("user-b")
    _agree(a)

    assert _schedules(a).status_code == 200
    assert _schedules(b).status_code == 428


def test_forbidden_request_has_no_side_effect(multi_user_e2e, enforced):
    a = multi_user_e2e.as_user("user-a")

    r = a.post(
        "/v1/schedules",
        json={"title": "막힌 요청", "start_time": "2024-01-01T09:00:00Z", "end_time": "2024-01-01T10:00:00Z"},
    )
    assert r.status_code == 428

    _agree(a)
    assert _schedules(a).json() == []


def test_disabled_setting_allows_requests(multi_user_e2e):
    a = multi_user_e2e.as_user("user-a")
    assert app_config.settings.CONSENT_ENFORCED is False
    assert _schedules(a).status_code == 200


def test_graphql_is_forbidden_until_consent(multi_user_e2e, enforced, monkeypatch):
    from app.core.auth import CurrentUser

    monkeypatch.setattr(CurrentUser, "mock", classmethod(lambda cls: multi_user_e2e.get_user("user-a")))
    a = multi_user_e2e.as_user("user-a")

    r = a.post("/v1/graphql", json={"query": "{ __typename }"})
    assert r.status_code == 428
    assert r.json()["message"] == "consent_required"

    _agree(a)
    assert a.post("/v1/graphql", json={"query": "{ __typename }"}).status_code == 200


def test_user_who_has_not_agreed_can_request_and_cancel_deletion(multi_user_e2e, enforced, monkeypatch):
    """새 약관에 동의하지 않아도 탈퇴할 수 있고, 휴면 중 동의가 필요해도 탈퇴를 취소할 수 있다"""
    monkeypatch.setattr(app_config.settings, "KRATOS_ADMIN_URL", "")  # 세션 폐기 호출 없이
    a = multi_user_e2e.as_user("user-a")
    _agree(a)
    monkeypatch.setattr(app_config.settings, "CONSENT_VERSION", "2099-01-01")
    assert _schedules(a).status_code == 403

    assert a.post("/v1/users/me/deletion").status_code == 200
    r = _schedules(a)
    assert r.status_code == 403
    assert r.json()["message"] == "account_deletion_pending"

    assert a.delete("/v1/users/me/deletion").status_code == 200
    r = _schedules(a)
    assert r.status_code == 403
    assert r.json()["message"] == "consent_required"

    _agree(a)
    assert _schedules(a).status_code == 200
