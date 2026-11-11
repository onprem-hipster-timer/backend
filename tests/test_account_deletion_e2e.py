"""
회원 탈퇴 신청·취소 E2E 테스트

- POST /v1/users/me/deletion: 휴면으로 바꾸고 Kratos 세션을 모두 폐기한다. 다시 보내도 처음 시각을 유지한다
- DELETE /v1/users/me/deletion: 휴면을 푼다
- 휴면 계정은 GET /v1/users/me와 탈퇴 신청·취소 외의 인증 요청에 403 account_deletion_pending
- 신청·취소마다 접근 기록 한 줄 (tests/core/test_audit.py가 형식을 지킨다)
"""
import json
import logging
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from starlette.websockets import WebSocketDisconnect

import app.core.config as app_config
from app.core import kratos_admin
from app.core.audit import AUDIT_LOGGER_NAME

KRATOS_ADMIN = "http://kratos-admin.test"


class FakeKratosAdmin:
    """받은 요청을 기록하고 status가 정한 코드로 답하는 가짜 Kratos admin API"""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.status = 204
        self.fail = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.fail:
            raise httpx.ConnectError("unreachable", request=request)
        if request.method == "GET" and request.url.path == "/admin/identities":
            return httpx.Response(200, json=[])
        return httpx.Response(self.status)

    def calls(self) -> list[tuple[str, str]]:
        """identity 목록 조회를 뺀 요청 (목록 조회는 tests/test_unverified_signup_cleanup.py가 본다)"""
        return [
            (r.method, r.url.path) for r in self.requests
            if not (r.method == "GET" and r.url.path == "/admin/identities")
        ]


@pytest.fixture
def kratos(monkeypatch, multi_user_e2e):
    fake = FakeKratosAdmin()
    monkeypatch.setattr(app_config.settings, "KRATOS_ADMIN_URL", KRATOS_ADMIN)
    monkeypatch.setattr(
        kratos_admin,
        "_make_client",
        lambda: httpx.AsyncClient(base_url=KRATOS_ADMIN, transport=httpx.MockTransport(fake)),
    )
    return fake


class AuditRecords(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines: list[dict] = []

    def emit(self, record):
        self.lines.append(json.loads(record.getMessage()))


@pytest.fixture
def audit(monkeypatch):
    handler = AuditRecords()
    logger = logging.getLogger(AUDIT_LOGGER_NAME)
    # alembic env.py의 fileConfig가 같은 프로세스의 기존 로거를 끈다 (마이그레이션 테스트)
    monkeypatch.setattr(logger, "disabled", False)
    logger.addHandler(handler)
    try:
        yield handler
    finally:
        logger.removeHandler(handler)


def _parse(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S%z")


class TestRequestAndCancel:
    def test_profile_shows_no_deletion_by_default(self, multi_user_e2e):
        data = multi_user_e2e.as_user("user-a").get("/v1/users/me").json()
        assert data["deletion_requested_at"] is None
        assert data["deletion_scheduled_at"] is None

    def test_request_marks_dormant_and_schedules_after_grace(self, multi_user_e2e, kratos):
        a = multi_user_e2e.as_user("user-a")
        before = datetime.now(timezone.utc).replace(microsecond=0)

        r = a.post("/v1/users/me/deletion")

        assert r.status_code == 200
        data = r.json()
        requested = _parse(data["deletion_requested_at"])
        scheduled = _parse(data["deletion_scheduled_at"])
        assert before <= requested <= datetime.now(timezone.utc)
        assert scheduled - requested == timedelta(days=app_config.settings.ACCOUNT_DELETION_GRACE_DAYS)
        assert a.get("/v1/users/me").json()["deletion_requested_at"] == data["deletion_requested_at"]

    def test_schedule_follows_grace_setting(self, multi_user_e2e, kratos, monkeypatch):
        monkeypatch.setattr(app_config.settings, "ACCOUNT_DELETION_GRACE_DAYS", 7)
        data = multi_user_e2e.as_user("user-a").post("/v1/users/me/deletion").json()

        assert _parse(data["deletion_scheduled_at"]) - _parse(data["deletion_requested_at"]) == timedelta(days=7)

    def test_grace_days_default_is_three(self):
        assert app_config.Settings().ACCOUNT_DELETION_GRACE_DAYS == 3

    def test_rerequest_keeps_original_time(self, multi_user_e2e, kratos, audit):
        a = multi_user_e2e.as_user("user-a")
        first = a.post("/v1/users/me/deletion").json()["deletion_requested_at"]

        again = a.post("/v1/users/me/deletion")

        assert again.status_code == 200
        assert again.json()["deletion_requested_at"] == first
        assert [line["event"] for line in audit.lines] == ["deletion_requested"]
        assert len(kratos.requests) == 1

    def test_request_revokes_all_kratos_sessions(self, multi_user_e2e, kratos):
        a = multi_user_e2e.as_user("user-a")

        a.post("/v1/users/me/deletion")

        assert kratos.calls() == [("DELETE", "/admin/identities/user-a/sessions")]

    @pytest.mark.parametrize("status_code", [404, 500])
    def test_session_revoke_error_does_not_block_request(self, multi_user_e2e, kratos, status_code):
        kratos.status = status_code
        a = multi_user_e2e.as_user("user-a")

        r = a.post("/v1/users/me/deletion")

        assert r.status_code == 200
        assert a.get("/v1/users/me").json()["deletion_requested_at"] is not None

    def test_unreachable_kratos_does_not_block_request(self, multi_user_e2e, kratos):
        kratos.fail = True
        a = multi_user_e2e.as_user("user-a")

        assert a.post("/v1/users/me/deletion").status_code == 200
        assert a.get("/v1/users/me").json()["deletion_requested_at"] is not None

    def test_no_admin_url_skips_session_revoke(self, multi_user_e2e, kratos, monkeypatch):
        monkeypatch.setattr(app_config.settings, "KRATOS_ADMIN_URL", "")
        a = multi_user_e2e.as_user("user-a")

        assert a.post("/v1/users/me/deletion").status_code == 200
        assert kratos.requests == []

    def test_cancel_restores_account(self, multi_user_e2e, kratos):
        a = multi_user_e2e.as_user("user-a")
        a.post("/v1/users/me/deletion")

        r = a.delete("/v1/users/me/deletion")

        assert r.status_code == 200
        assert r.json()["deletion_requested_at"] is None
        assert r.json()["deletion_scheduled_at"] is None
        assert a.get("/v1/todos").status_code == 200

    def test_cancel_without_request_is_noop(self, multi_user_e2e, audit):
        a = multi_user_e2e.as_user("user-a")

        r = a.delete("/v1/users/me/deletion")

        assert r.status_code == 200
        assert r.json()["deletion_requested_at"] is None
        assert audit.lines == []

    def test_request_after_cancel_starts_new_grace(self, multi_user_e2e, kratos):
        a = multi_user_e2e.as_user("user-a")
        a.post("/v1/users/me/deletion")
        a.delete("/v1/users/me/deletion")

        r = a.post("/v1/users/me/deletion")

        assert r.json()["deletion_requested_at"] is not None
        assert kratos.calls() == [("DELETE", "/admin/identities/user-a/sessions")] * 2


class TestDormantOwnRequests:
    @pytest.fixture
    def dormant(self, multi_user_e2e, kratos):
        a = multi_user_e2e.as_user("user-a")
        assert a.post("/v1/users/me/deletion").status_code == 200
        return a

    @pytest.mark.parametrize(
        ("method", "path", "body"),
        [
            ("get", "/v1/todos", None),
            ("get", "/v1/tags/groups", None),
            ("get", "/v1/timers", None),
            ("get", "/v1/meetings", None),
            ("get", "/v1/friends", None),
            ("get", "/v1/friends/requests/received", None),
            ("post", "/v1/schedules", {"title": "x", "start_time": "2024-01-01T10:00:00Z", "end_time": "2024-01-01T11:00:00Z"}),
            ("put", "/v1/users/me/consent", {"version": "x", "age_over_14": True, "terms": True, "privacy": True}),
        ],
    )
    def test_other_endpoints_are_forbidden(self, dormant, method, path, body):
        kwargs = {"json": body} if body is not None else {}
        r = getattr(dormant, method)(path, **kwargs)

        assert r.status_code == 423
        assert r.json()["message"] == "account_deletion_pending"

    def test_profile_and_cancel_are_allowed(self, dormant):
        assert dormant.get("/v1/users/me").status_code == 200
        assert dormant.post("/v1/users/me/deletion").status_code == 200
        assert dormant.delete("/v1/users/me/deletion").status_code == 200

    def test_public_endpoints_are_unaffected(self, dormant):
        assert dormant.get("/health").status_code == 200

    def test_graphql_is_forbidden(self, dormant, multi_user_e2e, monkeypatch):
        from app.core.auth import CurrentUser
        monkeypatch.setattr(
            CurrentUser, "mock", classmethod(lambda cls: multi_user_e2e.get_user("user-a"))
        )

        r = dormant.post("/v1/graphql", json={"query": "{ __typename }"})

        assert r.status_code == 423
        assert r.json()["message"] == "account_deletion_pending"

    def test_graphql_allowed_for_active_user(self, multi_user_e2e, monkeypatch):
        from app.core.auth import CurrentUser
        monkeypatch.setattr(
            CurrentUser, "mock", classmethod(lambda cls: multi_user_e2e.get_user("user-b"))
        )
        b = multi_user_e2e.as_user("user-b")
        b.get("/v1/users/me")

        r = b.post("/v1/graphql", json={"query": "{ __typename }"})

        assert r.status_code == 200

    def test_websocket_is_refused(self, dormant, multi_user_e2e):
        dormant._set_user_override()
        client = multi_user_e2e._client

        with client.websocket_connect("/v1/ws/timers") as ws:
            with pytest.raises(WebSocketDisconnect) as closed:
                ws.receive_json()

        assert closed.value.code == 1008

    def test_websocket_allowed_after_cancel(self, dormant, multi_user_e2e):
        dormant.delete("/v1/users/me/deletion")
        dormant._set_user_override()

        with multi_user_e2e._client.websocket_connect("/v1/ws/timers") as ws:
            assert ws.receive_json()["type"] == "connected"


class TestAuditLog:
    def test_request_and_cancel_are_logged(self, multi_user_e2e, kratos, audit):
        a = multi_user_e2e.as_user("user-a", email="private@example.com")
        a.get("/v1/users/me")

        a.post("/v1/users/me/deletion")
        a.delete("/v1/users/me/deletion")

        assert [line["event"] for line in audit.lines] == ["deletion_requested", "deletion_cancelled"]
        for line in audit.lines:
            assert set(line) == {"audit", "event", "identity_id", "ip", "at"}
            assert line["audit"] == "account_access"
            assert line["identity_id"] == "user-a"
            assert line["ip"] == "testclient"
            assert "private@example.com" not in json.dumps(line)
