"""이메일 인증을 마치지 않은 가입 정보 정리 (POST /internal/accounts/purge)

가입 뒤 UNVERIFIED_SIGNUP_RETENTION_HOURS가 지나도 이메일을 인증하지 않은 Kratos identity를 지운다.
"""
from datetime import UTC, datetime, timedelta

import httpx
import pytest

import app.core.config as app_config
from app.core import kratos_admin
from tests.test_account_deletion_e2e import AuditRecords, KRATOS_ADMIN
from tests.test_account_purge_e2e import PURGE, TOKEN


def _identity(identity_id: str, age: timedelta, verified: bool) -> dict:
    created = datetime.now(UTC) - age
    return {
        "id": identity_id,
        "created_at": created.isoformat().replace("+00:00", "Z"),
        "verifiable_addresses": [
            {"value": f"{identity_id}@example.com", "via": "email", "verified": verified},
        ],
    }


class FakeKratosIdentities:
    """identity 목록(페이지 단위)과 삭제 요청을 흉내 내는 가짜 Kratos admin API"""

    def __init__(self):
        self.pages: list[list[dict]] = [[]]
        self.deleted: list[str] = []
        self.list_status = 200
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if request.method == "GET" and path == "/admin/identities":
            if self.list_status != 200:
                return httpx.Response(self.list_status)
            index = int(request.url.params.get("page_token") or 0)
            headers = {}
            if index + 1 < len(self.pages):
                headers["Link"] = f'<{KRATOS_ADMIN}/admin/identities?page_size=250&page_token={index + 1}>; rel="next"'
            return httpx.Response(200, json=self.pages[index], headers=headers)
        if request.method == "DELETE" and path.startswith("/admin/identities/"):
            self.deleted.append(path.rsplit("/", 1)[-1])
            return httpx.Response(204)
        return httpx.Response(204)


@pytest.fixture
def kratos(monkeypatch, multi_user_e2e):
    fake = FakeKratosIdentities()
    monkeypatch.setattr(app_config.settings, "KRATOS_ADMIN_URL", KRATOS_ADMIN)
    monkeypatch.setattr(app_config.settings, "ACCOUNT_PURGE_TOKEN", TOKEN)
    monkeypatch.setattr(
        kratos_admin,
        "_make_client",
        lambda: httpx.AsyncClient(base_url=KRATOS_ADMIN, transport=httpx.MockTransport(fake)),
    )
    return fake


def _run(multi_user_e2e) -> dict:
    r = multi_user_e2e._client.post(PURGE, headers={"X-Purge-Token": TOKEN})
    assert r.status_code == 200, r.text
    return r.json()


def _retention() -> timedelta:
    return timedelta(hours=app_config.settings.UNVERIFIED_SIGNUP_RETENTION_HOURS)


def test_retention_default_is_one_day():
    assert app_config.Settings().UNVERIFIED_SIGNUP_RETENTION_HOURS == 24


def test_old_unverified_signup_is_deleted(multi_user_e2e, kratos):
    kratos.pages = [[_identity("stale", _retention() + timedelta(minutes=1), verified=False)]]

    assert _run(multi_user_e2e)["unverified_removed"] == 1
    assert kratos.deleted == ["stale"]


def test_recent_unverified_signup_is_kept(multi_user_e2e, kratos):
    kratos.pages = [[_identity("fresh", _retention() - timedelta(minutes=1), verified=False)]]

    assert _run(multi_user_e2e)["unverified_removed"] == 0
    assert kratos.deleted == []


def test_verified_identity_is_kept(multi_user_e2e, kratos):
    kratos.pages = [[_identity("member", timedelta(days=30), verified=True)]]

    assert _run(multi_user_e2e)["unverified_removed"] == 0
    assert kratos.deleted == []


def test_identity_without_addresses_is_kept(multi_user_e2e, kratos):
    identity = _identity("no-address", timedelta(days=30), verified=False)
    identity["verifiable_addresses"] = []
    kratos.pages = [[identity]]

    assert _run(multi_user_e2e)["unverified_removed"] == 0
    assert kratos.deleted == []


def test_guest_identity_is_kept(multi_user_e2e, kratos):
    """게스트 identity의 handle은 인증된 주소라 미인증 가입 정리 대상이 아니다"""
    identity = _identity("guest", timedelta(days=30), verified=True)
    identity["verifiable_addresses"][0]["value"] = "6f1c2a9e-3b4d-4e5f-8a7b-9c0d1e2f3a4b@guest.invalid"
    kratos.pages = [[identity]]

    assert _run(multi_user_e2e)["unverified_removed"] == 0
    assert kratos.deleted == []


def test_identity_that_has_used_the_service_is_kept(multi_user_e2e, kratos):
    """인증되지 않은 것으로 보여도 서비스 프로필이 있는 계정은 지우지 아니한다"""
    multi_user_e2e.as_user("used").get("/v1/users/me")
    kratos.pages = [[_identity("used", timedelta(days=30), verified=False)]]

    assert _run(multi_user_e2e)["unverified_removed"] == 0
    assert kratos.deleted == []


def test_all_pages_are_checked(multi_user_e2e, kratos):
    old = _retention() + timedelta(hours=1)
    kratos.pages = [
        [_identity("a", old, verified=False), _identity("b", old, verified=True)],
        [_identity("c", old, verified=False)],
    ]

    assert _run(multi_user_e2e)["unverified_removed"] == 2
    assert sorted(kratos.deleted) == ["a", "c"]


def test_listing_failure_does_not_fail_the_run(multi_user_e2e, kratos):
    kratos.list_status = 500

    result = _run(multi_user_e2e)

    assert result["unverified_removed"] == 0
    assert kratos.deleted == []


def test_skipped_without_admin_url(multi_user_e2e, kratos, monkeypatch):
    monkeypatch.setattr(app_config.settings, "KRATOS_ADMIN_URL", "")

    assert _run(multi_user_e2e)["unverified_removed"] == 0
    assert kratos.requests == []


def test_removal_is_logged_without_email(multi_user_e2e, kratos, monkeypatch):
    import logging

    from app.core.audit import AUDIT_LOGGER_NAME

    handler = AuditRecords()
    logger = logging.getLogger(AUDIT_LOGGER_NAME)
    monkeypatch.setattr(logger, "disabled", False)
    logger.addHandler(handler)
    try:
        kratos.pages = [[_identity("stale", _retention() + timedelta(minutes=1), verified=False)]]
        _run(multi_user_e2e)
    finally:
        logger.removeHandler(handler)

    assert [(l["event"], l["identity_id"], l["ip"]) for l in handler.lines] == [("signup_expired", "stale", None)]
    assert "example.com" not in str(handler.lines)
