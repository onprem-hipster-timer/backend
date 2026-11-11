"""
회원 탈퇴 파기 (POST /internal/accounts/purge) E2E 테스트

- X-Purge-Token이 ACCOUNT_PURGE_TOKEN과 같아야 한다. 설정이 비어 있으면 404
- 신청 시각 + ACCOUNT_DELETION_GRACE_DAYS가 지난 계정만 파기한다
- 그 sub의 데이터와 다른 사용자 데이터 속 그 sub의 흔적(허용 목록, 미팅 참여, 친구 관계)을 지우고
  다른 사용자의 데이터는 남긴다
- DB 커밋 뒤 Kratos identity를 지운다. 404는 성공, 실패하면 다음 실행이 다시 시도한다
- 파기한 sub의 토큰은 401이고 프로필을 다시 만들지 않는다
"""
import json
import logging
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import func
from sqlmodel import Session, select

import app.core.config as app_config
from app.core.audit import AUDIT_LOGGER_NAME
from app.db.session import _session_manager
from app.domain.user import purge
from app.models import (
    AccountDeletion,
    Friendship,
    Meeting,
    MeetingParticipant,
    MeetingTimeSlot,
    ResourceVisibility,
    Schedule,
    ScheduleException,
    ScheduleExceptionTag,
    ScheduleTag,
    Tag,
    TagGroup,
    TimerSession,
    Todo,
    TodoTag,
    UserProfile,
    VisibilityAllowEmail,
    VisibilityAllowList,
)
from app.models.base import utc_now_naive
from app.models.tag import TimerTag
from tests.conftest import TimerCommands
from tests.test_account_deletion_e2e import AuditRecords, FakeKratosAdmin, KRATOS_ADMIN
from tests.test_account_deletion_hidden_e2e import _befriend, _code, _make_meeting, _participate

TOKEN = "purge-token-for-tests"
PURGE = "/internal/accounts/purge"


@pytest.fixture
def kratos(monkeypatch, multi_user_e2e):
    import httpx
    from app.core import kratos_admin

    fake = FakeKratosAdmin()
    monkeypatch.setattr(app_config.settings, "KRATOS_ADMIN_URL", KRATOS_ADMIN)
    monkeypatch.setattr(app_config.settings, "ACCOUNT_PURGE_TOKEN", TOKEN)
    monkeypatch.setattr(
        kratos_admin,
        "_make_client",
        lambda: httpx.AsyncClient(base_url=KRATOS_ADMIN, transport=httpx.MockTransport(fake)),
    )
    return fake


@pytest.fixture
def audit(monkeypatch):
    handler = AuditRecords()
    logger = logging.getLogger(AUDIT_LOGGER_NAME)
    monkeypatch.setattr(logger, "disabled", False)
    logger.addHandler(handler)
    try:
        yield handler
    finally:
        logger.removeHandler(handler)


def _db() -> Session:
    return Session(_session_manager.engine)


def _set_requested_at(sub: str, age: timedelta) -> None:
    with _db() as session:
        profile = session.get(UserProfile, sub)
        profile.deletion_requested_at = utc_now_naive() - age
        session.add(profile)
        session.commit()


def _grace() -> timedelta:
    return timedelta(days=app_config.settings.ACCOUNT_DELETION_GRACE_DAYS)


def _request_and_age(client, sub: str, age: timedelta) -> None:
    assert client.post("/v1/users/me/deletion").status_code == 200
    _set_requested_at(sub, age)


def _run(multi_user_e2e) -> dict:
    r = multi_user_e2e._client.post(PURGE, headers={"X-Purge-Token": TOKEN})
    assert r.status_code == 200, r.text
    return r.json()


class TestEndpointAuth:
    def test_disabled_when_token_setting_empty(self, multi_user_e2e, monkeypatch):
        monkeypatch.setattr(app_config.settings, "ACCOUNT_PURGE_TOKEN", "")

        r = multi_user_e2e._client.post(PURGE, headers={"X-Purge-Token": ""})

        assert r.status_code == 404

    @pytest.mark.parametrize("headers", [{}, {"X-Purge-Token": "wrong"}, {"X-Purge-Token": TOKEN + "x"}, {"X-Purge-Token": ""}])
    def test_rejects_missing_or_wrong_token(self, multi_user_e2e, kratos, headers):
        a = multi_user_e2e.as_user("user-a")
        _request_and_age(a, "user-a", _grace() + timedelta(minutes=1))

        r = multi_user_e2e._client.post(PURGE, headers=headers)

        assert r.status_code == 401
        with _db() as session:
            assert session.get(UserProfile, "user-a") is not None

    def test_correct_token_returns_counts_only(self, multi_user_e2e, kratos):
        assert _run(multi_user_e2e) == {"purged": 0, "kratos_pending": 0, "unverified_removed": 0}

    def test_get_not_allowed(self, multi_user_e2e, kratos):
        assert multi_user_e2e._client.get(PURGE, headers={"X-Purge-Token": TOKEN}).status_code == 405

    def test_not_in_openapi_schema(self, multi_user_e2e):
        from app.main import app

        assert not [path for path in app.openapi()["paths"] if path.startswith("/internal")]


class TestGraceBoundary:
    def test_not_purged_just_before_grace_ends(self, multi_user_e2e, kratos):
        a = multi_user_e2e.as_user("user-a")
        _request_and_age(a, "user-a", _grace() - timedelta(minutes=1))

        assert _run(multi_user_e2e) == {"purged": 0, "kratos_pending": 0, "unverified_removed": 0}
        assert a.get("/v1/users/me").status_code == 200
        assert ("DELETE", "/admin/identities/user-a") not in kratos.calls()

    def test_purged_just_after_grace_ends(self, multi_user_e2e, kratos):
        a = multi_user_e2e.as_user("user-a")
        _request_and_age(a, "user-a", _grace() + timedelta(minutes=1))

        assert _run(multi_user_e2e) == {"purged": 1, "kratos_pending": 0, "unverified_removed": 0}

    @pytest.mark.parametrize("days", [1, 7])
    def test_boundary_follows_setting(self, multi_user_e2e, kratos, monkeypatch, days):
        monkeypatch.setattr(app_config.settings, "ACCOUNT_DELETION_GRACE_DAYS", days)
        a = multi_user_e2e.as_user("user-a")
        b = multi_user_e2e.as_user("user-b")
        _request_and_age(a, "user-a", timedelta(days=days) + timedelta(minutes=1))
        _request_and_age(b, "user-b", timedelta(days=days) - timedelta(minutes=1))

        assert _run(multi_user_e2e) == {"purged": 1, "kratos_pending": 0, "unverified_removed": 0}
        with _db() as session:
            assert session.get(UserProfile, "user-a") is None
            assert session.get(UserProfile, "user-b") is not None

    def test_active_and_cancelled_accounts_are_kept(self, multi_user_e2e, kratos):
        a = multi_user_e2e.as_user("user-a")
        b = multi_user_e2e.as_user("user-b")
        b.get("/v1/users/me")
        _request_and_age(a, "user-a", _grace() + timedelta(days=10))
        a.delete("/v1/users/me/deletion")

        assert _run(multi_user_e2e)["purged"] == 0
        assert a.get("/v1/todos").status_code == 200
        assert b.get("/v1/todos").status_code == 200


def _populate(multi_user_e2e):
    """a(파기 대상)와 b·c·d의 데이터. a의 흔적이 다른 사용자 데이터에도 남게 만든다."""
    a = multi_user_e2e.as_user("user-a", email="alice@example.com")
    b = multi_user_e2e.as_user("user-b", email="b@example.com")
    c = multi_user_e2e.as_user("user-c", email="c@example.com")
    d = multi_user_e2e.as_user("user-d", email="d@example.com")
    for client in (a, b, c, d):
        client.get("/v1/users/me")
    _befriend(a, b)
    _befriend(b, d)
    a.post("/v1/friends/requests", json={"friend_code": _code(c)})
    assert d.post("/v1/friends/block/user-a").status_code in (200, 201)

    # a: 태그 그룹·태그, 반복 일정과 예외(태그), Todo 부모·자식(태그), 타이머(태그)
    group_id = a.post("/v1/tags/groups", json={"name": "업무", "color": "#FF5733"}).json()["id"]
    tag_id = a.post("/v1/tags", json={"name": "중요", "color": "#00FF00", "group_id": group_id}).json()["id"]
    schedule = a.post("/v1/schedules", json={
        "title": "반복", "start_time": "2024-01-01T10:00:00Z", "end_time": "2024-01-01T11:00:00Z",
        "recurrence_rule": "FREQ=DAILY;COUNT=5", "tag_ids": [tag_id],
    })
    assert schedule.status_code == 201, schedule.text
    schedule_id = schedule.json()["id"]
    exception = a.patch(
        f"/v1/schedules/{schedule_id}",
        params={"instance_start": "2024-01-02T10:00:00Z"},
        json={"title": "예외", "tag_ids": [tag_id]},
    )
    assert exception.status_code == 200, exception.text
    parent_id = a.post("/v1/todos", json={"title": "부모", "tag_group_id": group_id, "tag_ids": [tag_id]}).json()["id"]
    child = a.post("/v1/todos", json={"title": "자식", "tag_group_id": group_id, "parent_id": parent_id,
                                     "deadline": "2024-01-03T10:00:00Z"})
    assert child.status_code == 201, child.text
    timer_id = TimerCommands(a).create_timer(title="타이머", allocated_duration=600, tag_ids=[tag_id])["id"]
    a.put(f"/v1/visibility/schedule/{schedule_id}", json={"level": "selected", "allowed_user_ids": ["user-b"]})
    a.put(f"/v1/visibility/timer/{timer_id}", json={"level": "friends"})
    a.put(f"/v1/visibility/todo/{parent_id}", json={"level": "public"})

    # a 소유 미팅에 b가 참여
    a_meeting = _make_meeting(a)
    a.put(f"/v1/visibility/meeting/{a_meeting}", json={"level": "public"})
    _participate(b, a_meeting, "B")

    # b의 일정: a와 d를 허용 목록에
    b_schedule = b.post("/v1/schedules", json={
        "title": "b 일정", "start_time": "2024-01-01T10:00:00Z", "end_time": "2024-01-01T11:00:00Z",
    }).json()["id"]
    r = b.put(f"/v1/visibility/schedule/{b_schedule}", json={"level": "selected", "allowed_user_ids": ["user-a", "user-d"]})
    assert r.status_code == 200, r.text

    # c의 미팅: 이메일·도메인 허용, a와 b가 참여
    c_meeting = _make_meeting(c)
    r = c.put(f"/v1/visibility/meeting/{c_meeting}", json={
        "level": "allowed_emails", "allowed_emails": ["alice@example.com", "b@example.com"], "allowed_domains": ["example.com"],
    })
    assert r.status_code == 200, r.text
    _participate(a, c_meeting, "A")
    _participate(b, c_meeting, "B")

    return {"a": a, "b": b, "c": c, "b_schedule": b_schedule, "c_meeting": c_meeting, "a_meeting": a_meeting}


def _rows_with_sub(session: Session, sub: str) -> dict[str, int]:
    """sub가 남은 행 수 (표마다)"""
    def count(statement) -> int:
        return session.exec(select(func.count()).select_from(statement.subquery())).one()

    a_timers = select(TimerSession.id).where(TimerSession.owner_id == sub)
    a_schedules = select(Schedule.id).where(Schedule.owner_id == sub)
    a_exceptions = select(ScheduleException.id).where(ScheduleException.owner_id == sub)
    a_todos = select(Todo.id).where(Todo.owner_id == sub)
    a_tags = select(Tag.id).where(Tag.owner_id == sub)
    a_participants = select(MeetingParticipant.id).where(MeetingParticipant.user_id == sub)
    a_meetings = select(Meeting.id).where(Meeting.owner_id == sub)
    return {
        "user_profile": count(select(UserProfile).where(UserProfile.sub == sub)),
        "timersession": count(a_timers),
        "timer_tag": count(select(TimerTag).where(TimerTag.timer_id.in_(a_timers) | TimerTag.tag_id.in_(a_tags))),
        "schedule": count(a_schedules),
        "schedule_tag": count(select(ScheduleTag).where(ScheduleTag.tag_id.in_(a_tags))),
        "scheduleexception": count(a_exceptions),
        "schedule_exception_tag": count(select(ScheduleExceptionTag).where(ScheduleExceptionTag.tag_id.in_(a_tags))),
        "todo": count(a_todos),
        "todo_tag": count(select(TodoTag).where(TodoTag.tag_id.in_(a_tags))),
        "tag": count(a_tags),
        "tag_group": count(select(TagGroup).where(TagGroup.owner_id == sub)),
        "meeting": count(a_meetings),
        "meeting_participant": count(a_participants),
        "meeting_participant_in_own_meeting": count(
            select(MeetingParticipant).where(MeetingParticipant.meeting_id.in_(a_meetings))
        ),
        "meeting_time_slot": count(select(MeetingTimeSlot).where(MeetingTimeSlot.participant_id.in_(a_participants))),
        "resource_visibility": count(select(ResourceVisibility).where(ResourceVisibility.owner_id == sub)),
        "visibility_allow_list": count(select(VisibilityAllowList).where(VisibilityAllowList.allowed_user_id == sub)),
        "visibility_allow_email": count(select(VisibilityAllowEmail).where(func.lower(VisibilityAllowEmail.email) == "alice@example.com")),
        "friendship": count(select(Friendship).where((Friendship.requester_id == sub) | (Friendship.addressee_id == sub))),
    }


class TestPurgeDeletesEverything:
    def test_every_table_is_cleared_for_sub(self, multi_user_e2e, kratos):
        data = _populate(multi_user_e2e)
        with _db() as session:
            before = _rows_with_sub(session, "user-a")
        assert all(before.values()), before

        _request_and_age(data["a"], "user-a", _grace() + timedelta(minutes=1))
        assert _run(multi_user_e2e) == {"purged": 1, "kratos_pending": 0, "unverified_removed": 0}

        with _db() as session:
            assert _rows_with_sub(session, "user-a") == dict.fromkeys(before, 0)
            assert session.get(AccountDeletion, "user-a") is not None

    def test_other_users_data_is_kept(self, multi_user_e2e, kratos):
        data = _populate(multi_user_e2e)
        b, c = data["b"], data["c"]
        _request_and_age(data["a"], "user-a", _grace() + timedelta(minutes=1))

        _run(multi_user_e2e)

        assert b.get(f"/v1/schedules/{data['b_schedule']}").status_code == 200
        assert b.get(f"/v1/visibility/schedule/{data['b_schedule']}").json()["allowed_user_ids"] == ["user-d"]
        assert b.get("/v1/friends/ids").json() == ["user-d"]
        visibility = c.get(f"/v1/visibility/meeting/{data['c_meeting']}").json()
        assert visibility["allowed_emails"] == ["b@example.com"]
        assert visibility["allowed_domains"] == ["example.com"]
        availability = c.get(f"/v1/meetings/{data['c_meeting']}/availability").json()
        assert [item["participant"]["display_name"] for item in availability] == ["B"]
        assert len(availability[0]["time_slots"]) == 1
        assert b.get(f"/v1/meetings/{data['a_meeting']}").status_code == 404
        with _db() as session:
            for sub in ("user-b", "user-c", "user-d"):
                assert session.get(UserProfile, sub) is not None
            assert session.exec(select(func.count()).select_from(Meeting)).one() == 1
            b_participants = session.exec(select(MeetingParticipant).where(MeetingParticipant.user_id == "user-b")).all()
            assert [p.meeting_id for p in b_participants] == [UUID(data["c_meeting"])]

    def test_purged_token_is_rejected_without_new_profile(self, multi_user_e2e, kratos):
        a = multi_user_e2e.as_user("user-a")
        _request_and_age(a, "user-a", _grace() + timedelta(minutes=1))
        _run(multi_user_e2e)

        for method, path in (("get", "/v1/users/me"), ("get", "/v1/todos"), ("delete", "/v1/users/me/deletion")):
            r = getattr(a, method)(path)
            assert r.status_code == 401
            assert r.json()["message"] == "account_deleted"
        with _db() as session:
            assert session.get(UserProfile, "user-a") is None

    def test_purged_websocket_is_refused(self, multi_user_e2e, kratos):
        from starlette.websockets import WebSocketDisconnect

        a = multi_user_e2e.as_user("user-a")
        _request_and_age(a, "user-a", _grace() + timedelta(minutes=1))
        _run(multi_user_e2e)
        a._set_user_override()

        with multi_user_e2e._client.websocket_connect("/v1/ws/timers") as ws:
            with pytest.raises(WebSocketDisconnect) as closed:
                ws.receive_json()
        assert closed.value.code == 1008

    def test_double_purge_is_idempotent(self, multi_user_e2e, kratos):
        data = _populate(multi_user_e2e)
        _request_and_age(data["a"], "user-a", _grace() + timedelta(minutes=1))

        assert _run(multi_user_e2e) == {"purged": 1, "kratos_pending": 0, "unverified_removed": 0}
        assert _run(multi_user_e2e) == {"purged": 0, "kratos_pending": 0, "unverified_removed": 0}
        assert kratos.calls() == [
            ("DELETE", "/admin/identities/user-a/sessions"),
            ("DELETE", "/admin/identities/user-a"),
        ]

    def test_second_runner_skips_account_already_taken(self, multi_user_e2e, kratos):
        """다른 실행이 먼저 파기 기록을 남긴 계정은 건드리지 않는다"""
        a = multi_user_e2e.as_user("user-a")
        a.post("/v1/tags/groups", json={"name": "업무", "color": "#FF5733"})
        _request_and_age(a, "user-a", _grace() + timedelta(minutes=1))
        with _db() as session:
            session.add(AccountDeletion(sub="user-a", purged_at=utc_now_naive()))
            session.commit()

        with _db() as session:
            assert purge.purge_account(session, "user-a", utc_now_naive() - _grace()) is False
        with _db() as session:
            assert session.get(UserProfile, "user-a") is not None
            assert session.exec(select(TagGroup).where(TagGroup.owner_id == "user-a")).first() is not None

    def test_purge_account_rechecks_cancellation(self, multi_user_e2e, kratos):
        a = multi_user_e2e.as_user("user-a")
        _request_and_age(a, "user-a", _grace() + timedelta(minutes=1))
        a.delete("/v1/users/me/deletion")

        with _db() as session:
            assert purge.purge_account(session, "user-a", utc_now_naive() - _grace()) is False
        assert a.get("/v1/todos").status_code == 200

    def test_failure_for_one_account_does_not_stop_others(self, multi_user_e2e, kratos, monkeypatch):
        a = multi_user_e2e.as_user("user-a")
        b = multi_user_e2e.as_user("user-b")
        _request_and_age(a, "user-a", _grace() + timedelta(minutes=2))
        _request_and_age(b, "user-b", _grace() + timedelta(minutes=1))
        original = purge.delete_user_data

        def failing(session, sub, verified_email):
            if sub == "user-a":
                raise RuntimeError("boom")
            return original(session, sub, verified_email)

        monkeypatch.setattr(purge, "delete_user_data", failing)

        assert _run(multi_user_e2e) == {"purged": 1, "kratos_pending": 0, "unverified_removed": 0}
        with _db() as session:
            assert session.get(UserProfile, "user-a") is not None
            assert session.get(UserProfile, "user-b") is None


class TestKratosIdentity:
    def test_404_counts_as_deleted(self, multi_user_e2e, kratos):
        a = multi_user_e2e.as_user("user-a")
        _request_and_age(a, "user-a", _grace() + timedelta(minutes=1))
        kratos.status = 404

        assert _run(multi_user_e2e) == {"purged": 1, "kratos_pending": 0, "unverified_removed": 0}
        with _db() as session:
            assert session.get(AccountDeletion, "user-a").kratos_deleted_at is not None

    @pytest.mark.parametrize("failure", ["status", "unreachable", "no_admin_url"])
    def test_failure_is_retried_next_run(self, multi_user_e2e, kratos, monkeypatch, failure):
        a = multi_user_e2e.as_user("user-a")
        _request_and_age(a, "user-a", _grace() + timedelta(minutes=1))
        kratos.requests.clear()
        if failure == "status":
            kratos.status = 500
        elif failure == "unreachable":
            kratos.fail = True
        else:
            monkeypatch.setattr(app_config.settings, "KRATOS_ADMIN_URL", "")

        assert _run(multi_user_e2e) == {"purged": 1, "kratos_pending": 1, "unverified_removed": 0}
        with _db() as session:
            assert session.get(UserProfile, "user-a") is None
            assert session.get(AccountDeletion, "user-a").kratos_deleted_at is None
        assert a.get("/v1/users/me").status_code == 401

        kratos.status = 204
        kratos.fail = False
        monkeypatch.setattr(app_config.settings, "KRATOS_ADMIN_URL", KRATOS_ADMIN)
        kratos.requests.clear()

        assert _run(multi_user_e2e) == {"purged": 0, "kratos_pending": 0, "unverified_removed": 0}
        assert kratos.calls() == [("DELETE", "/admin/identities/user-a")]
        assert _run(multi_user_e2e) == {"purged": 0, "kratos_pending": 0, "unverified_removed": 0}
        assert kratos.calls() == [("DELETE", "/admin/identities/user-a")]

    def test_record_kept_one_day_after_identity_deleted(self, multi_user_e2e, kratos):
        a = multi_user_e2e.as_user("user-a")
        _request_and_age(a, "user-a", _grace() + timedelta(minutes=1))
        _run(multi_user_e2e)

        def age_record(age: timedelta) -> None:
            with _db() as session:
                record = session.get(AccountDeletion, "user-a")
                record.kratos_deleted_at = utc_now_naive() - age
                session.add(record)
                session.commit()

        age_record(purge.DELETED_ACCOUNT_RETENTION - timedelta(minutes=1))
        _run(multi_user_e2e)
        with _db() as session:
            assert session.get(AccountDeletion, "user-a") is not None

        age_record(purge.DELETED_ACCOUNT_RETENTION + timedelta(minutes=1))
        _run(multi_user_e2e)
        with _db() as session:
            assert session.get(AccountDeletion, "user-a") is None


class TestAuditLog:
    def test_purge_is_logged_without_ip_or_email(self, multi_user_e2e, kratos, audit):
        a = multi_user_e2e.as_user("user-a", email="private@example.com")
        _request_and_age(a, "user-a", _grace() + timedelta(minutes=1))
        audit.lines.clear()

        _run(multi_user_e2e)

        assert len(audit.lines) == 1
        line = audit.lines[0]
        assert set(line) == {"audit", "event", "identity_id", "ip", "at"}
        assert line["event"] == "account_purged"
        assert line["identity_id"] == "user-a"
        assert line["ip"] is None
        assert "private@example.com" not in json.dumps(line)


class TestAllowedEmailMatching:
    def test_entries_typed_with_other_case_are_removed(self, multi_user_e2e, kratos):
        """다른 사용자가 대소문자를 섞어 입력한 탈퇴자의 이메일도 파기 때 지워지고, 다른 주소는 남는다"""
        a = multi_user_e2e.as_user("user-a", email="alice@example.com")
        b = multi_user_e2e.as_user("user-b", email="b@example.com")
        a.get("/v1/users/me")
        schedule_id = b.post(
            "/v1/schedules",
            json={"title": "공유", "start_time": "2024-01-01T09:00:00Z", "end_time": "2024-01-01T10:00:00Z"},
        ).json()["id"]
        r = b.put(
            f"/v1/visibility/schedule/{schedule_id}",
            json={"level": "allowed_emails", "allowed_emails": ["Alice@Example.COM", "carol@example.com"]},
        )
        assert r.status_code == 200, r.text
        _request_and_age(a, "user-a", _grace() + timedelta(minutes=1))

        assert _run(multi_user_e2e)["purged"] == 1

        remaining = b.get(f"/v1/visibility/schedule/{schedule_id}").json()["allowed_emails"]
        assert [e.lower() for e in remaining] == ["carol@example.com"]
