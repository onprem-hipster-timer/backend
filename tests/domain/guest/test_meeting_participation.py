"""게스트의 미팅 참여와 가능 시간 (app/domain/meeting/visitor_service.py MeetingGuestService)

- 게스트당 참여자 하나. 표시 이름은 게스트 이름이고 보낸 display_name은 쓰지 않는다
- 게스트는 자기 참여자의 가능 시간만 바꾼다. 다른 참여자는 없는 참여자와 같은 404
- 게스트가 폐기되면 그 참여자와 가능 시간이 사라진다
- 미팅을 지우면 그 미팅의 게스트를 폐기한다. 소유자를 파기하면 하루 한 번 실행이 폐기한다(MISSING)
"""
import uuid
from datetime import timedelta

import pytest
from sqlmodel import select

import app.core.config as app_config
from app.db.session import _session_manager
from app.models.base import utc_now_naive
from app.models.meeting import MeetingParticipant, MeetingTimeSlot
from app.models.user_profile import UserProfile
from tests.domain.guest.helpers import guest_rows, make_guest
from tests.domain.guest.meeting_helpers import (
    CELL_COUNT,
    MEMBER,
    OWNER,
    SLOT,
    cell_count,
    create_meeting,
    participate,
    set_slots,
)


@pytest.fixture
def client(guest_client, meeting_host):
    return guest_client


@pytest.fixture
def meeting_id(client, tokens) -> str:
    return create_meeting(client, tokens)


@pytest.fixture
def guest(kratos, meeting_id):
    return make_guest(kratos, uuid.UUID(meeting_id), "민수")


def _participants() -> list[MeetingParticipant]:
    with _session_manager.get_session() as session:
        return list(session.exec(select(MeetingParticipant)).all())


def _slot_count(participant_id: str) -> int:
    with _session_manager.get_session() as session:
        statement = select(MeetingTimeSlot).where(MeetingTimeSlot.participant_id == uuid.UUID(participant_id))
        return len(session.exec(statement).all())


class TestParticipate:
    def test_first_call_creates_participant_named_after_guest(self, client, tokens, meeting_id, guest):
        response = client.post(
            f"/v1/meetings/{meeting_id}/participate",
            json={"display_name": "다른 이름"},
            headers=tokens.guest(guest.identity_id),
        )

        assert response.status_code == 201
        body = response.json()
        assert body["display_name"] == "민수"
        assert body["user_id"] is None
        assert body["meeting_id"] == meeting_id
        assert [(p.guest_id, p.user_id) for p in _participants()] == [(guest.id, None)]

    def test_repeated_call_returns_same_participant(self, client, tokens, meeting_id, guest):
        headers = tokens.guest(guest.identity_id)
        first = participate(client, meeting_id, headers)

        response = client.post(
            f"/v1/meetings/{meeting_id}/participate", json={"display_name": "또 다른 이름"}, headers=headers,
        )

        assert response.status_code == 200
        assert response.json()["id"] == first["id"]
        assert response.json()["display_name"] == "민수"
        assert len(_participants()) == 1

    def test_guest_and_member_with_same_name_are_separate(self, client, tokens, meeting_id, guest):
        guest_participant = participate(client, meeting_id, tokens.guest(guest.identity_id))
        member_participant = participate(client, meeting_id, tokens.member(MEMBER), name="민수")

        assert guest_participant["id"] != member_participant["id"]
        assert member_participant["user_id"] == MEMBER
        assert len(_participants()) == 2

    def test_body_rules_still_apply(self, client, tokens, meeting_id, guest):
        response = client.post(
            f"/v1/meetings/{meeting_id}/participate", json={}, headers=tokens.guest(guest.identity_id),
        )

        assert response.status_code == 422
        assert _participants() == []


class TestAvailability:
    def test_guest_sets_own_slots_and_they_count(self, client, tokens, meeting_id, guest):
        headers = tokens.guest(guest.identity_id)
        participant = participate(client, meeting_id, headers)

        response = set_slots(client, meeting_id, participant["id"], headers)

        assert response.status_code == 200
        assert [s["participant_id"] for s in response.json()] == [participant["id"]]
        assert cell_count(client.get(f"/v1/meetings/{meeting_id}/result").json()) == 1

    def test_replacing_slots_replaces_all(self, client, tokens, meeting_id, guest):
        headers = tokens.guest(guest.identity_id)
        participant = participate(client, meeting_id, headers)
        set_slots(client, meeting_id, participant["id"], headers)

        assert set_slots(client, meeting_id, participant["id"], headers, slots=[]).status_code == 200

        assert _slot_count(participant["id"]) == 0

    def test_other_participants_are_not_found(self, client, tokens, kratos, meeting_id, guest):
        headers = tokens.guest(guest.identity_id)
        participate(client, meeting_id, headers)
        member = participate(client, meeting_id, tokens.member(MEMBER))
        set_slots(client, meeting_id, member["id"], tokens.member(MEMBER))
        other = make_guest(kratos, uuid.UUID(meeting_id), "지수")
        other_participant = participate(client, meeting_id, tokens.guest(other.identity_id))
        missing = set_slots(client, meeting_id, str(uuid.uuid4()), headers)

        for participant_id in (member["id"], other_participant["id"]):
            response = set_slots(client, meeting_id, participant_id, headers, slots=[])
            assert response.status_code == 404
            assert response.json()["error_type"] == "MeetingParticipantNotFoundError"
            assert {k: v for k, v in response.json().items() if k not in ("error_id", "timestamp")} == {
                k: v for k, v in missing.json().items() if k not in ("error_id", "timestamp")
            }
        assert _slot_count(member["id"]) == 1

    def test_member_cannot_set_guest_participant(self, client, tokens, meeting_id, guest):
        guest_participant = participate(client, meeting_id, tokens.guest(guest.identity_id))
        set_slots(client, meeting_id, guest_participant["id"], tokens.guest(guest.identity_id))

        response = set_slots(client, meeting_id, guest_participant["id"], tokens.member(MEMBER), slots=[])

        assert response.status_code == 404
        assert _slot_count(guest_participant["id"]) == 1

    def test_slot_count_limit(self, client, tokens, meeting_id, guest):
        headers = tokens.guest(guest.identity_id)
        participant = participate(client, meeting_id, headers)
        set_slots(client, meeting_id, participant["id"], headers)

        response = set_slots(client, meeting_id, participant["id"], headers, slots=[SLOT] * (CELL_COUNT + 1))

        assert response.status_code == 422
        assert response.json()["error_type"] == "TooManyTimeSlotsError"
        assert _slot_count(participant["id"]) == 1

    def test_guest_sees_own_entry_in_availability(self, client, tokens, meeting_id, guest):
        headers = tokens.guest(guest.identity_id)
        participant = participate(client, meeting_id, headers)
        set_slots(client, meeting_id, participant["id"], headers)

        availability = client.get(f"/v1/meetings/{meeting_id}/availability", headers=headers).json()

        assert [(a["participant"]["id"], a["participant"]["display_name"], len(a["time_slots"])) for a in availability] == [
            (participant["id"], "민수", 1)
        ]


class TestGuestRemoval:
    def test_self_deletion_removes_participant_and_slots(self, client, tokens, meeting_id, guest):
        headers = tokens.guest(guest.identity_id)
        participant = participate(client, meeting_id, headers)
        set_slots(client, meeting_id, participant["id"], headers)
        member = participate(client, meeting_id, tokens.member(MEMBER))

        assert client.delete("/v1/guests/me", headers={**headers, "X-Turnstile-Token": "t"}).status_code == 204

        availability = client.get(f"/v1/meetings/{meeting_id}/availability", headers=tokens.member(MEMBER)).json()
        assert [a["participant"]["id"] for a in availability] == [member["id"]]
        assert _slot_count(participant["id"]) == 0
        assert cell_count(client.get(f"/v1/meetings/{meeting_id}/result").json()) == 0


class TestMeetingRemoval:
    def test_deleting_meeting_discards_only_its_guests(self, client, tokens, kratos, meeting_id, guest):
        participant = participate(client, meeting_id, tokens.guest(guest.identity_id))
        set_slots(client, meeting_id, participant["id"], tokens.guest(guest.identity_id))
        other_meeting = create_meeting(client, tokens)
        other = make_guest(kratos, uuid.UUID(other_meeting), "지수")

        response = client.delete(f"/v1/meetings/{meeting_id}", headers=tokens.member(OWNER))

        assert response.status_code == 200
        assert [g.id for g in guest_rows()] == [other.id]
        assert kratos.deleted == [guest.identity_id]
        assert _participants() == []
        assert client.get(f"/v1/meetings/{other_meeting}", headers=tokens.guest(other.identity_id)).status_code == 200

    def test_refused_delete_keeps_guests(self, client, tokens, kratos, meeting_id, guest):
        response = client.delete(f"/v1/meetings/{meeting_id}", headers=tokens.member(MEMBER))

        assert response.status_code == 404
        assert [g.id for g in guest_rows()] == [guest.id]
        assert kratos.deleted == []

    def test_owner_purge_and_daily_run_discard_guests(self, client, tokens, kratos, meeting_id, guest, monkeypatch):
        """소유자를 파기하면 미팅이 지워지고(MISSING) 같은 하루 한 번 실행이 그 게스트를 폐기한다"""
        participate(client, meeting_id, tokens.guest(guest.identity_id))
        assert client.post("/v1/users/me/deletion", headers=tokens.member(OWNER)).status_code == 200
        with _session_manager.get_session() as session:
            profile = session.get(UserProfile, OWNER)
            profile.deletion_requested_at = utc_now_naive() - timedelta(
                days=app_config.settings.ACCOUNT_DELETION_GRACE_DAYS + 1
            )
            session.add(profile)
            session.commit()
        monkeypatch.setattr(app_config.settings, "ACCOUNT_PURGE_TOKEN", "purge-token")

        response = client.post("/internal/accounts/purge", headers={"X-Purge-Token": "purge-token"})

        assert response.status_code == 200
        assert response.json()["purged"] == 1
        assert response.json()["guests_discarded"] == 1
        assert guest_rows() == []
        assert guest.identity_id in kratos.deleted
        assert _participants() == []
