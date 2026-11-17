"""회원이 게스트의 가능 시간을 가져온다 (POST /v1/meetings/{meeting_id}/guest-import)

- 회원 경로다. 본문의 guest_token(그 미팅 게스트의 JWT)이 그 게스트를 쥐고 있다는 증명이다
- 회원 참여자(없으면 프로필 표시 이름으로 만든다)에 게스트 참여자의 가능 시간을 합치고 게스트를 폐기한다.
  DB에 닿는 것(참여자 생성, 가능 시간, 게스트 행·참여자·가능 시간·약관 동의 삭제)은 한 트랜잭션이고,
  Kratos identity는 커밋한 뒤 지운다
- 회원이 미팅에 접근할 수 없으면 404 MeetingNotFoundError, 게스트가 없거나 다른 미팅의 게스트면 404 GuestNotFoundError,
  게스트 토큰이 아니거나 검증에 실패하면 422 GuestTokenInvalidError
"""
import time
import uuid
from datetime import datetime

import pytest
from sqlmodel import select

import app.core.config as app_config
from app.crud import meeting as meeting_crud
from app.db.session import _session_manager
from app.domain.consent import service as consent_service
from app.domain.guest import service as guest_service
from app.domain.guest.events import GuestDiscarded
from app.domain.meeting import guest_host
from app.domain.meeting import service as meeting_service
from app.domain.meeting.schema.dto import TimeSlotCreate, _validate_kinds_do_not_overlap
from app.models.meeting import Meeting, MeetingParticipant, MeetingTimeSlot
from tests.domain.guest.conftest import Tokens
from tests.domain.guest.helpers import consent_body, consent_rows, guest_rows, make_guest
from tests.domain.guest.meeting_helpers import (
    CELL_COUNT,
    MEETING,
    MEMBER,
    OWNER,
    create_meeting,
    guest_routes,
    call,
    participate,
    set_allow_guests,
    set_level,
    set_slots,
    without_request_values,
)

TURNSTILE = {"X-Turnstile-Token": "t"}


@pytest.fixture
def client(guest_client, meeting_host):
    return guest_client


@pytest.fixture
def meeting_id(client, tokens) -> str:
    return create_meeting(client, tokens)


@pytest.fixture
def guest(kratos, meeting_id):
    return make_guest(kratos, uuid.UUID(meeting_id), "민수")


def _slot(day: int, start: str, end: str, kind: str = "available") -> dict:
    return {"start_time": f"2099-03-0{day}T{start}:00Z", "end_time": f"2099-03-0{day}T{end}:00Z", "kind": kind}


def _read(day: int, start: str, end: str, kind: str = "available") -> tuple:
    """응답(UTC)의 가능 시간 모양"""
    return f"2099-03-0{day}T{start}:00+0000", f"2099-03-0{day}T{end}:00+0000", kind


def _answer(slots: list[dict]) -> list[tuple]:
    return sorted((s["start_time"], s["end_time"], s["kind"]) for s in slots)


def _member(tokens, name: str | None = None, sub: str = MEMBER) -> dict:
    """회원 토큰. name이 있으면 name 클레임(프로필 표시 이름)을 넣는다"""
    claims = {"email": f"{sub}@example.com", "email_verified": True}
    if name is not None:
        claims["name"] = name
    return {"Authorization": f"Bearer {tokens.make(sub, 'default', **claims)}"}


def _guest_token(tokens, guest, **claims) -> str:
    return tokens.make(guest.identity_id, "guest", name="게스트", **claims)


def _answer_as_guest(client, tokens, meeting_id, guest, slots: list[dict]) -> str:
    headers = tokens.guest(guest.identity_id)
    participant_id = participate(client, meeting_id, headers)["id"]
    assert set_slots(client, meeting_id, participant_id, headers, slots).status_code == 200
    return participant_id


def _answer_as_member(client, tokens, meeting_id, slots: list[dict], name: str = "회원", sub: str = MEMBER) -> str:
    headers = tokens.member(sub)
    participant_id = participate(client, meeting_id, headers, name=name)["id"]
    assert set_slots(client, meeting_id, participant_id, headers, slots).status_code == 200
    return participant_id


def _import(client, tokens, meeting_id, guest_token, headers: dict | None = None, **kwargs):
    return client.post(
        f"/v1/meetings/{meeting_id}/guest-import",
        json={"guest_token": guest_token},
        headers=tokens.member(MEMBER) if headers is None else headers,
        **kwargs,
    )


def _participants() -> list[tuple]:
    with _session_manager.get_session() as session:
        return sorted(
            (str(p.id), p.user_id, str(p.guest_id) if p.guest_id else None, p.display_name)
            for p in session.exec(select(MeetingParticipant)).all()
        )


def _slots() -> list[tuple]:
    with _session_manager.get_session() as session:
        return sorted(
            (str(s.participant_id), s.start_time, s.end_time, s.kind.value)
            for s in session.exec(select(MeetingTimeSlot)).all()
        )


def _snapshot(kratos) -> tuple:
    """DB에 닿는 모든 것과 Kratos identity"""
    return _participants(), _slots(), [g.id for g in guest_rows()], consent_rows(), sorted(kratos.identities)


def _result(client, meeting_id) -> dict:
    return client.get(f"/v1/meetings/{meeting_id}/result").json()


def _grid(result: dict) -> list[tuple]:
    return [(c["start_time"], c["count"], c["unavailable_count"]) for c in result["availability_grid"]]


def _meeting_row(meeting_id: str) -> Meeting:
    with _session_manager.get_session() as session:
        meeting = session.get(Meeting, uuid.UUID(meeting_id))
        session.expunge(meeting)
        return meeting


def _assert_valid_answer(meeting_id: str, slots: list[dict]) -> None:
    """저장 규칙 중 겹침과 하루 범위 규칙을 지킨다 (슬롯 수 제한은 보지 않는다)"""
    answer = [TimeSlotCreate(**s) for s in slots]
    _validate_kinds_do_not_overlap(answer)
    assert meeting_service._first_uncovered_day(_meeting_row(meeting_id), answer) is None


# ============ 가져오기 ============

class TestImport:
    def test_member_not_yet_participant_gets_participant_named_after_profile(
            self, client, tokens, kratos, meeting_id, guest, guest_events,
    ):
        guest_participant = _answer_as_guest(client, tokens, meeting_id, guest, [
            _slot(2, "09:00", "10:00"), _slot(3, "09:00", "10:00", "unavailable"), _slot(3, "10:00", "11:00"),
        ])

        response = _import(client, tokens, meeting_id, _guest_token(tokens, guest), headers=_member(tokens, "회원 이름"))

        assert response.status_code == 200, response.text
        body = response.json()
        participant = body["participant"]
        assert (participant["user_id"], participant["display_name"]) == (MEMBER, "회원 이름")
        assert (participant["meeting_id"], participant["is_guest"], participant["is_owner"]) == (meeting_id, False, False)
        assert participant["id"] != guest_participant
        assert _answer(body["time_slots"]) == [
            _read(2, "09:00", "10:00"), _read(3, "09:00", "10:00", "unavailable"), _read(3, "10:00", "11:00"),
        ]
        assert {s["participant_id"] for s in body["time_slots"]} == {participant["id"]}
        assert [(p[1], p[2]) for p in _participants()] == [(MEMBER, None)]
        assert {s[0] for s in _slots()} == {participant["id"]}
        assert guest_rows() == []
        assert kratos.deleted == [guest.identity_id]
        assert [(type(e), e.guest_id) for e in guest_events] == [(GuestDiscarded, guest.id)]

    def test_member_without_profile_name_gets_guest_name(self, client, tokens, meeting_id, guest):
        _answer_as_guest(client, tokens, meeting_id, guest, [_slot(2, "09:00", "10:00")])

        response = _import(client, tokens, meeting_id, _guest_token(tokens, guest), headers=_member(tokens))

        assert response.status_code == 200
        assert response.json()["participant"]["display_name"] == "민수"

    def test_profile_name_breaking_participant_rules_falls_back_to_guest_name(self, client, tokens, meeting_id, guest):
        response = _import(client, tokens, meeting_id, _guest_token(tokens, guest), headers=_member(tokens, "가" * 51))

        assert response.status_code == 200
        assert response.json()["participant"]["display_name"] == "민수"

    def test_guest_without_participant_leaves_member_answer_and_is_discarded(
            self, client, tokens, kratos, meeting_id, guest,
    ):
        member_participant = _answer_as_member(client, tokens, meeting_id, [_slot(2, "09:00", "10:00")])

        response = _import(client, tokens, meeting_id, _guest_token(tokens, guest))

        assert response.status_code == 200
        assert response.json()["participant"]["id"] == member_participant
        assert _answer(response.json()["time_slots"]) == [_read(2, "09:00", "10:00")]
        assert guest_rows() == []
        assert kratos.deleted == [guest.identity_id]

    def test_existing_participant_keeps_id_and_display_name(self, client, tokens, meeting_id, guest):
        member_participant = _answer_as_member(client, tokens, meeting_id, [_slot(2, "09:00", "10:00")], name="원래 이름")
        _answer_as_guest(client, tokens, meeting_id, guest, [_slot(2, "09:30", "11:00"), _slot(4, "09:00", "10:00")])

        response = _import(client, tokens, meeting_id, _guest_token(tokens, guest), headers=_member(tokens, "다른 이름"))

        assert response.status_code == 200
        participant = response.json()["participant"]
        assert (participant["id"], participant["display_name"]) == (member_participant, "원래 이름")
        assert _answer(response.json()["time_slots"]) == [_read(2, "09:00", "11:00"), _read(4, "09:00", "10:00")]

    def test_member_answer_wins_where_kinds_overlap(self, client, tokens, meeting_id, guest):
        _answer_as_member(client, tokens, meeting_id, [
            _slot(2, "09:00", "10:00", "unavailable"), _slot(2, "10:00", "11:00"),  # 2일: 불가능 → 가능
            _slot(3, "09:00", "10:00"),  # 3일: 가능만
        ])
        _answer_as_guest(client, tokens, meeting_id, guest, [
            _slot(2, "09:00", "11:00"),  # 회원의 불가능(09–10)과 겹친다
            _slot(3, "09:00", "11:00", "unavailable"),  # 회원의 가능(09–10)과 겹친다
        ])

        response = _import(client, tokens, meeting_id, _guest_token(tokens, guest))

        assert response.status_code == 200
        slots = response.json()["time_slots"]
        assert _answer(slots) == [
            _read(2, "09:00", "10:00", "unavailable"), _read(2, "10:00", "11:00"),
            _read(3, "09:00", "10:00"), _read(3, "10:00", "11:00", "unavailable"),
        ]
        _assert_valid_answer(meeting_id, slots)

    def test_response_matches_availability_read_and_takes_timezone(self, client, tokens, meeting_id, guest):
        _answer_as_guest(client, tokens, meeting_id, guest, [_slot(2, "09:00", "10:00")])

        response = _import(client, tokens, meeting_id, _guest_token(tokens, guest), params={"timezone": "Asia/Seoul"})

        assert response.status_code == 200
        availability = client.get(
            f"/v1/meetings/{meeting_id}/availability", params={"timezone": "Asia/Seoul"}, headers=tokens.member(MEMBER),
        ).json()
        assert availability == [response.json()]
        assert response.json()["time_slots"][0]["start_time"] == "2099-03-02T18:00:00+0900"

    def test_result_counts_after_import_equal_the_union(self, client, tokens, meeting_id, guest):
        member_slots = [_slot(2, "09:00", "10:00"), _slot(3, "09:00", "10:00", "unavailable"), _slot(3, "10:00", "11:00")]
        guest_slots = [_slot(2, "09:00", "11:00"), _slot(4, "10:00", "11:00", "unavailable"), _slot(4, "09:00", "10:00")]
        _answer_as_member(client, tokens, meeting_id, member_slots)
        _answer_as_guest(client, tokens, meeting_id, guest, guest_slots)
        before = _result(client, meeting_id)
        assert before["participant_count"] == 2

        assert _import(client, tokens, meeting_id, _guest_token(tokens, guest)).status_code == 200

        after = _result(client, meeting_id)
        assert after["participant_count"] == 1
        assert [cell[0] for cell in _grid(after)] == [cell[0] for cell in _grid(before)]
        # 회원과 게스트가 같은 칸에 같은 종류로 답했으면 한 명이 되고, 한쪽만 답한 칸은 그대로 한 명이다
        assert _grid(after) == [(start, min(count, 1), min(unavailable, 1)) for start, count, unavailable in _grid(before)]
        assert sum(count for _, count, _ in _grid(after)) == 4
        assert sum(unavailable for _, _, unavailable in _grid(after)) == 2

    def test_guest_row_participant_slots_consent_and_identity_are_gone(self, client, tokens, kratos, meeting_id, guest):
        guest_participant = _answer_as_guest(client, tokens, meeting_id, guest, [_slot(2, "09:00", "10:00")])
        assert client.put(
            "/v1/guests/me/consent", json=consent_body(), headers=tokens.guest(guest.identity_id),
        ).status_code == 204
        assert (guest.identity_id, app_config.settings.CONSENT_VERSION) in consent_rows()

        assert _import(client, tokens, meeting_id, _guest_token(tokens, guest)).status_code == 200

        assert guest_rows() == []
        assert guest_participant not in {p[0] for p in _participants()}
        assert guest_participant not in {s[0] for s in _slots()}
        assert all(sub != guest.identity_id for sub, _ in consent_rows())
        assert guest.identity_id not in kratos.identities
        for method, url, body in guest_routes(meeting_id):
            assert call(client, method, url, body, tokens.guest(guest.identity_id)).status_code == 403, (method, url)

    def test_other_guests_and_participants_are_kept(self, client, tokens, kratos, meeting_id, guest):
        other = make_guest(kratos, uuid.UUID(meeting_id), "지수")
        other_participant = _answer_as_guest(client, tokens, meeting_id, other, [_slot(2, "09:00", "10:00")])
        owner_participant = _answer_as_member(client, tokens, meeting_id, [_slot(3, "09:00", "10:00")], sub=OWNER)

        assert _import(client, tokens, meeting_id, _guest_token(tokens, guest)).status_code == 200

        assert [g.id for g in guest_rows()] == [other.id]
        assert {other_participant, owner_participant} <= {p[0] for p in _participants()}
        assert kratos.deleted == [guest.identity_id]

    def test_slot_count_limit_is_not_applied(self, client, tokens, meeting_id, guest):
        _answer_as_member(client, tokens, meeting_id, [
            _slot(day, start, end) for day in range(2, 7) for start, end in (("09:00", "09:10"), ("10:50", "11:00"))
        ])
        _answer_as_guest(client, tokens, meeting_id, guest, [
            _slot(day, start, end) for day in range(2, 7) for start, end in (("09:20", "09:30"), ("10:20", "10:30"))
        ])

        response = _import(client, tokens, meeting_id, _guest_token(tokens, guest))

        assert response.status_code == 200
        assert len(response.json()["time_slots"]) == 2 * CELL_COUNT > CELL_COUNT


class TestDayCoverage:
    def test_hourly_answers_stay_valid(self, client, tokens, meeting_id, guest):
        _answer_as_member(client, tokens, meeting_id, [_slot(2, "09:00", "10:00"), _slot(3, "09:00", "11:00", "unavailable")])
        _answer_as_guest(client, tokens, meeting_id, guest, [
            _slot(2, "09:00", "11:00", "unavailable"), _slot(3, "10:00", "11:00"), _slot(4, "09:30", "10:00"),
        ])

        response = _import(client, tokens, meeting_id, _guest_token(tokens, guest))

        slots = response.json()["time_slots"]
        assert _answer(slots) == [
            _read(2, "09:00", "10:00"), _read(2, "10:00", "11:00", "unavailable"),
            _read(3, "09:00", "11:00", "unavailable"), _read(4, "09:30", "10:00"),
        ]
        _assert_valid_answer(meeting_id, slots)

    def test_hourly_day_left_uncovered_after_range_change_is_filled_with_unavailable(
            self, client, tokens, meeting_id, guest,
    ):
        _answer_as_member(client, tokens, meeting_id, [_slot(2, "09:00", "10:00", "unavailable"), _slot(2, "10:00", "11:00")])
        _answer_as_guest(client, tokens, meeting_id, guest, [_slot(3, "09:00", "10:00")])
        response = client.patch(f"/v1/meetings/{meeting_id}", json={"end_time": "12:00:00"}, headers=tokens.member(OWNER))
        assert response.status_code == 200

        response = _import(client, tokens, meeting_id, _guest_token(tokens, guest))

        slots = response.json()["time_slots"]
        assert _answer(slots) == [
            _read(2, "09:00", "10:00", "unavailable"), _read(2, "10:00", "11:00"),
            _read(2, "11:00", "12:00", "unavailable"), _read(3, "09:00", "10:00"),
        ]
        _assert_valid_answer(meeting_id, slots)

    @pytest.fixture
    def daily_meeting(self, client, tokens) -> str:
        """2099-03-02~04, 하루 전체. hourly로 만들어 답을 받은 뒤 daily로 바꿀 수 있다"""
        body = {**MEETING, "end_date": "2099-03-04", "start_time": "00:00:00", "end_time": "00:00:00"}
        response = client.post("/v1/meetings", json=body, headers=tokens.member(OWNER))
        assert response.status_code == 201, response.text
        meeting_id = response.json()["id"]
        set_level(client, tokens, meeting_id, "public")
        set_allow_guests(client, tokens, meeting_id, True)
        return meeting_id

    @staticmethod
    def _day(day: int, kind: str = "available") -> dict:
        return {"start_time": f"2099-03-0{day}T00:00:00Z", "end_time": f"2099-03-0{day + 1}T00:00:00Z", "kind": kind}

    @staticmethod
    def _read_day(day: int, kind: str = "available", until: int | None = None) -> tuple:
        return f"2099-03-0{day}T00:00:00+0000", f"2099-03-0{(until or day) + 1}T00:00:00+0000", kind

    def _set_mode(self, client, tokens, meeting_id, mode: str) -> None:
        response = client.patch(f"/v1/meetings/{meeting_id}", json={"mode": mode}, headers=tokens.member(OWNER))
        assert response.status_code == 200, response.text

    def test_daily_answers_stay_valid(self, client, tokens, kratos, daily_meeting):
        self._set_mode(client, tokens, daily_meeting, "daily")
        guest = make_guest(kratos, uuid.UUID(daily_meeting), "민수")
        _answer_as_member(client, tokens, daily_meeting, [self._day(3)])
        _answer_as_guest(client, tokens, daily_meeting, guest, [
            self._day(2), self._day(3, "unavailable"), self._day(4, "unavailable"),
        ])

        response = _import(client, tokens, daily_meeting, _guest_token(tokens, guest))

        slots = response.json()["time_slots"]
        assert _answer(slots) == [self._read_day(2, until=3), self._read_day(4, "unavailable")]
        _assert_valid_answer(daily_meeting, slots)

    def test_daily_days_left_uncovered_after_mode_change_are_filled_with_unavailable(
            self, client, tokens, kratos, daily_meeting,
    ):
        """회원은 hourly일 때 첫날만 불가능으로 답했다. daily에서는 모든 날을 채워야 한다"""
        _answer_as_member(client, tokens, daily_meeting, [self._day(2, "unavailable")])
        self._set_mode(client, tokens, daily_meeting, "daily")
        guest = make_guest(kratos, uuid.UUID(daily_meeting), "민수")
        _answer_as_guest(client, tokens, daily_meeting, guest, [self._day(3)])

        response = _import(client, tokens, daily_meeting, _guest_token(tokens, guest))

        slots = response.json()["time_slots"]
        assert _answer(slots) == [
            self._read_day(2, "unavailable"), self._read_day(3), self._read_day(4, "unavailable"),
        ]
        _assert_valid_answer(daily_meeting, slots)


# ============ 게스트 상태 ============

class TestGuestState:
    def test_closed_guest_is_imported(self, client, tokens, kratos, meeting_id, guest):
        _answer_as_guest(client, tokens, meeting_id, guest, [_slot(2, "09:00", "10:00")])
        set_allow_guests(client, tokens, meeting_id, False)

        response = _import(client, tokens, meeting_id, _guest_token(tokens, guest))

        assert response.status_code == 200
        assert _answer(response.json()["time_slots"]) == [_read(2, "09:00", "10:00")]
        assert guest_rows() == []
        assert kratos.deleted == [guest.identity_id]

    def test_expired_guest_is_discarded_and_not_found(self, client, tokens, kratos, meeting_id, guest, monkeypatch):
        member_participant = _answer_as_member(client, tokens, meeting_id, [_slot(3, "09:00", "10:00")])
        _answer_as_guest(client, tokens, meeting_id, guest, [_slot(2, "09:00", "10:00")])
        monkeypatch.setattr(guest_host, "utc_now_naive", lambda: datetime(2099, 4, 6))

        response = _import(client, tokens, meeting_id, _guest_token(tokens, guest))

        assert (response.status_code, response.json()["error_type"]) == (404, "GuestNotFoundError")
        assert guest_rows() == []
        assert kratos.deleted == [guest.identity_id]
        assert [p[0] for p in _participants()] == [member_participant]
        assert [(s[0], s[1].day) for s in _slots()] == [(member_participant, 3)]


# ============ 거절 ============

class TestRefused:
    def test_member_without_access_gets_same_404_as_missing_meeting(self, client, tokens, kratos, meeting_id, guest):
        _answer_as_guest(client, tokens, meeting_id, guest, [_slot(2, "09:00", "10:00")])
        set_level(client, tokens, meeting_id, "allowed_emails")  # MEMBER는 허용 목록에 없다
        before = _snapshot(kratos)

        refused = _import(client, tokens, meeting_id, _guest_token(tokens, guest))
        missing = _import(client, tokens, uuid.uuid4(), _guest_token(tokens, guest))

        assert (refused.status_code, refused.json()["error_type"]) == (404, "MeetingNotFoundError")
        assert without_request_values(refused) == without_request_values(missing)
        assert _snapshot(kratos) == before

    def test_member_without_access_gets_404_before_token_is_read(self, client, tokens, kratos, meeting_id, guest):
        set_level(client, tokens, meeting_id, "allowed_emails")

        response = _import(client, tokens, meeting_id, "garbage")

        assert (response.status_code, response.json()["error_type"]) == (404, "MeetingNotFoundError")

    def test_guest_of_other_meeting_is_same_404_as_discarded_guest(self, client, tokens, kratos, meeting_id, guest):
        other_meeting = create_meeting(client, tokens)
        other = make_guest(kratos, uuid.UUID(other_meeting), "지수")
        _answer_as_guest(client, tokens, other_meeting, other, [_slot(2, "09:00", "10:00")])
        gone = make_guest(kratos, uuid.UUID(meeting_id), "철수")
        assert client.delete("/v1/guests/me", headers={**tokens.guest(gone.identity_id), **TURNSTILE}).status_code == 204
        before = _snapshot(kratos)

        crossed = _import(client, tokens, meeting_id, _guest_token(tokens, other))
        discarded = _import(client, tokens, meeting_id, _guest_token(tokens, gone))

        assert (crossed.status_code, crossed.json()["error_type"]) == (404, "GuestNotFoundError")
        assert without_request_values(crossed) == without_request_values(discarded)
        assert _snapshot(kratos) == before

    def test_repeat_call_is_not_found_and_changes_nothing(self, client, tokens, kratos, meeting_id, guest):
        _answer_as_guest(client, tokens, meeting_id, guest, [_slot(2, "09:00", "10:00")])
        token = _guest_token(tokens, guest)
        assert _import(client, tokens, meeting_id, token).status_code == 200
        before = _snapshot(kratos)

        again = _import(client, tokens, meeting_id, token)

        assert (again.status_code, again.json()["error_type"]) == (404, "GuestNotFoundError")
        assert _snapshot(kratos) == before
        assert kratos.deleted == [guest.identity_id]

    def test_guest_discarded_before_import_creates_no_participant(self, client, tokens, kratos, meeting_id, guest):
        _answer_as_guest(client, tokens, meeting_id, guest, [_slot(2, "09:00", "10:00")])
        assert client.delete("/v1/guests/me", headers={**tokens.guest(guest.identity_id), **TURNSTILE}).status_code == 204

        response = _import(client, tokens, meeting_id, _guest_token(tokens, guest))

        assert (response.status_code, response.json()["error_type"]) == (404, "GuestNotFoundError")
        assert _participants() == []

    def test_guest_discarded_between_check_and_transaction_is_not_found(
            self, client, tokens, kratos, meeting_id, guest, monkeypatch,
    ):
        """게스트 확인 뒤, 가져오기 트랜잭션이 게스트 행을 잠그기 전에 다른 요청이 게스트를 폐기했다"""
        _answer_as_guest(client, tokens, meeting_id, guest, [_slot(2, "09:00", "10:00")])
        read_status = guest_service._read_status

        def read_then_discard(resource_type, resource_id):
            status = read_status(resource_type, resource_id)
            guest_service._delete_guest_row(guest.identity_id)
            return status

        monkeypatch.setattr(guest_service, "_read_status", read_then_discard)

        response = _import(client, tokens, meeting_id, _guest_token(tokens, guest))

        assert (response.status_code, response.json()["error_type"]) == (404, "GuestNotFoundError")
        assert _participants() == []
        assert _slots() == []

    @pytest.mark.parametrize("make_token", [
        pytest.param(lambda tokens, guest: _guest_token(tokens, guest, exp=int(time.time()) - 5), id="expired"),
        pytest.param(lambda tokens, guest: "garbage", id="garbled"),
        pytest.param(lambda tokens, guest: "a.b.c", id="three-parts"),
        pytest.param(lambda tokens, guest: "", id="empty"),
        pytest.param(lambda tokens, guest: _guest_token(Tokens(), guest), id="other-key"),
        pytest.param(lambda tokens, guest: _guest_token(tokens, guest, iss="http://elsewhere/"), id="issuer"),
        pytest.param(lambda tokens, guest: _guest_token(tokens, guest, aud="http://elsewhere"), id="audience"),
        pytest.param(lambda tokens, guest: tokens.make(guest.identity_id, None), id="no-schema-id"),
        pytest.param(lambda tokens, guest: tokens.make(guest.identity_id, ""), id="empty-schema-id"),
        pytest.param(lambda tokens, guest: tokens.make(guest.identity_id, 1), id="number-schema-id"),
        pytest.param(lambda tokens, guest: tokens.make("", "guest"), id="no-sub"),
        pytest.param(lambda tokens, guest: tokens.make(MEMBER, "default", email="m@example.com"), id="member-token"),
        pytest.param(lambda tokens, guest: tokens.make(guest.identity_id, "default"), id="guest-sub-member-schema"),
    ])
    def test_token_that_is_not_a_valid_guest_token_is_422(self, client, tokens, kratos, meeting_id, guest, make_token):
        _answer_as_guest(client, tokens, meeting_id, guest, [_slot(2, "09:00", "10:00")])
        before = _snapshot(kratos)
        reference = _import(client, tokens, meeting_id, "garbage")

        response = _import(client, tokens, meeting_id, make_token(tokens, guest))

        assert (response.status_code, response.json()["error_type"]) == (422, "GuestTokenInvalidError")
        assert without_request_values(response) == without_request_values(reference)
        assert response.headers.get("www-authenticate") is None
        assert _snapshot(kratos) == before

    @pytest.mark.parametrize("body", [{}, {"guest_token": None}, {"guest_token": 1}, {"token": "x"}])
    def test_body_shape_is_checked(self, client, tokens, kratos, meeting_id, guest, body):
        before = _snapshot(kratos)

        response = client.post(f"/v1/meetings/{meeting_id}/guest-import", json=body, headers=tokens.member(MEMBER))

        assert response.status_code == 422
        assert "detail" in response.json()
        assert _snapshot(kratos) == before

    def test_guest_token_as_caller_is_403(self, client, tokens, kratos, meeting_id, guest):
        before = _snapshot(kratos)

        response = _import(client, tokens, meeting_id, _guest_token(tokens, guest), headers=tokens.guest(guest.identity_id))

        assert response.status_code == 403
        assert _snapshot(kratos) == before

    def test_without_token_is_401(self, client, tokens, kratos, meeting_id, guest):
        before = _snapshot(kratos)

        response = _import(client, tokens, meeting_id, _guest_token(tokens, guest), headers={})

        assert response.status_code == 401
        assert _snapshot(kratos) == before

    def test_member_consent_is_required(self, client, tokens, kratos, meeting_id, guest, monkeypatch):
        monkeypatch.setattr(app_config.settings, "CONSENT_ENFORCED", True)
        before = _snapshot(kratos)

        response = _import(client, tokens, meeting_id, _guest_token(tokens, guest))

        assert response.status_code == 428
        assert _snapshot(kratos) == before

    def test_guests_off_is_404(self, client, tokens, kratos, meeting_id, guest, guest_off):
        _answer_as_guest(client, tokens, meeting_id, guest, [_slot(2, "09:00", "10:00")])
        assert _import(client, tokens, meeting_id, "garbage").status_code == 422
        before = _snapshot(kratos)
        guest_off()

        response = _import(client, tokens, meeting_id, _guest_token(tokens, guest))

        assert response.status_code == 404
        assert _snapshot(kratos) == before


# ============ 한 트랜잭션 ============

class TestAtomic:
    """커밋 전 어느 단계에서 실패해도 아무것도 바뀌지 않고 게스트는 그대로 쓸 수 있다"""

    @pytest.fixture
    def answered(self, client, tokens, meeting_id, guest) -> str:
        _answer_as_guest(client, tokens, meeting_id, guest, [
            _slot(2, "09:00", "10:00"), _slot(3, "09:00", "10:00", "unavailable"), _slot(3, "10:00", "11:00"),
        ])
        assert client.put(
            "/v1/guests/me/consent", json=consent_body(), headers=tokens.guest(guest.identity_id),
        ).status_code == 204
        return meeting_id

    @staticmethod
    def _fail(patch: pytest.MonkeyPatch, stage: str) -> None:
        def fail(*args, **kwargs):
            raise RuntimeError(stage)

        def after(original):
            def run(*args, **kwargs):
                original(*args, **kwargs)
                raise RuntimeError(stage)
            return run

        if stage == "after participant creation":
            patch.setattr(meeting_service, "merge_time_slots", fail)
        elif stage == "after slot merge":
            patch.setattr(meeting_service, "replace_time_slots", after(meeting_service.replace_time_slots))
        elif stage == "after guest row deletion":
            patch.setattr(consent_service, "delete_consents", fail)
        elif stage == "after consent deletion":
            patch.setattr(consent_service, "delete_consents", after(consent_service.delete_consents))

    @pytest.mark.parametrize("stage", [
        "after participant creation", "after slot merge", "after guest row deletion", "after consent deletion",
    ])
    @pytest.mark.parametrize("member_joined", [False, True])
    def test_failure_before_commit_changes_nothing(self, client, tokens, kratos, answered, guest, stage, member_joined):
        meeting_id = answered
        if member_joined:
            _answer_as_member(client, tokens, meeting_id, [_slot(4, "09:00", "10:00")])
        before = _snapshot(kratos)

        with pytest.MonkeyPatch.context() as patch:
            self._fail(patch, stage)
            with pytest.raises(RuntimeError, match=stage):
                _import(client, tokens, meeting_id, _guest_token(tokens, guest))

        assert _snapshot(kratos) == before
        assert kratos.deleted == []
        availability = client.get(f"/v1/meetings/{meeting_id}/availability", headers=tokens.guest(guest.identity_id))
        assert availability.status_code == 200
        guest_entry = next(a for a in availability.json() if a["participant"]["is_guest"])
        assert len(guest_entry["time_slots"]) == 3

    def test_member_participant_created_meanwhile_is_409_and_changes_nothing(
            self, client, tokens, kratos, answered, guest, monkeypatch,
    ):
        """회원 참여자가 없다고 읽은 뒤 다른 요청이 먼저 만들었다. unique 제약이 막고 트랜잭션 전체가 되돌아간다"""
        meeting_id = answered
        _answer_as_member(client, tokens, meeting_id, [_slot(4, "09:00", "10:00")])
        before = _snapshot(kratos)
        find = meeting_crud.get_participant_by_user_id

        def miss_when_locking(session, meeting_id, user_id, lock=False):
            return None if lock else find(session, meeting_id, user_id)

        monkeypatch.setattr(meeting_crud, "get_participant_by_user_id", miss_when_locking)

        response = _import(client, tokens, meeting_id, _guest_token(tokens, guest))

        assert (response.status_code, response.json()["error_type"]) == (409, "GuestImportConflictError")
        assert _snapshot(kratos) == before
        assert kratos.deleted == []

    def test_import_after_a_failed_attempt_succeeds(self, client, tokens, kratos, answered, guest):
        meeting_id = answered
        with pytest.MonkeyPatch.context() as patch:
            self._fail(patch, "after guest row deletion")
            with pytest.raises(RuntimeError):
                _import(client, tokens, meeting_id, _guest_token(tokens, guest))

        response = _import(client, tokens, meeting_id, _guest_token(tokens, guest))

        assert response.status_code == 200
        assert len(response.json()["time_slots"]) == 3
        assert [(p[1], p[2]) for p in _participants()] == [(MEMBER, None)]
        assert guest_rows() == []

    def test_identity_delete_failure_after_commit_still_imports(self, client, tokens, kratos, answered, guest):
        meeting_id = answered
        kratos.down.add("admin")

        response = _import(client, tokens, meeting_id, _guest_token(tokens, guest))

        assert response.status_code == 200
        assert len(response.json()["time_slots"]) == 3
        assert guest_rows() == []
        assert guest.identity_id in kratos.identities
        assert kratos.deleted == []
        kratos.down.clear()
        for method, url, body in guest_routes(meeting_id):
            assert call(client, method, url, body, tokens.guest(guest.identity_id)).status_code == 403, (method, url)
        again = _import(client, tokens, meeting_id, _guest_token(tokens, guest))
        assert (again.status_code, again.json()["error_type"]) == (404, "GuestNotFoundError")

