"""미팅 생성자가 참여자를 빼기 (DELETE /v1/meetings/{meeting_id}/participants/{participant_id})

- 미팅 소유자만 뺀다(자기 참여자 포함). 다른 회원은 없는 미팅과 같은 404, 그 미팅의 참여자가 아니면 없는 참여자와 같은 404
- 회원 참여자는 지운다. 게스트 참여자는 그 게스트를 폐기한다: 게스트 행 삭제로 DB가 참여자·가능 시간을 지우고 Kratos identity를 지운다
- 회원만 쓰는 경로다. 게스트 토큰은 403, 토큰이 없으면 401, 휴면 소유자는 423, 동의하지 않은 소유자는 428
"""
import uuid

import pytest
from sqlmodel import select

import app.core.config as app_config
from app.db.session import _session_manager
from app.domain.guest.events import GuestDiscarded
from app.models.meeting import MeetingParticipant, MeetingTimeSlot
from tests.domain.guest.helpers import guest_rows, make_guest
from tests.domain.guest.meeting_helpers import (
    MEMBER,
    OWNER,
    call,
    cell_count,
    create_meeting,
    guest_routes,
    participate,
    set_allow_guests,
    set_slots,
    without_request_values,
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


@pytest.fixture
def participants(client, tokens, meeting_id, guest) -> dict:
    """생성자, 회원 MEMBER, 게스트가 참여해 모두 같은 가능 시간 하나를 넣었다"""
    ids = {}
    for key, headers, name in (
            ("owner", tokens.member(OWNER), "방장"),
            ("member", tokens.member(MEMBER), "회원"),
            ("guest", tokens.guest(guest.identity_id), "민수"),
    ):
        ids[key] = participate(client, meeting_id, headers, name=name)["id"]
        assert set_slots(client, meeting_id, ids[key], headers).status_code == 200
    return ids


def _remove(client, tokens, meeting_id, participant_id, headers: dict | None = None):
    return client.delete(
        f"/v1/meetings/{meeting_id}/participants/{participant_id}",
        headers=tokens.member(OWNER) if headers is None else headers,
    )


def _participant_ids() -> set[str]:
    with _session_manager.get_session() as session:
        return {str(p.id) for p in session.exec(select(MeetingParticipant)).all()}


def _slot_participant_ids() -> list[str]:
    """가능 시간 행마다 그 참여자 id"""
    with _session_manager.get_session() as session:
        return sorted(str(s.participant_id) for s in session.exec(select(MeetingTimeSlot)).all())


def _result(client, meeting_id) -> dict:
    return client.get(f"/v1/meetings/{meeting_id}/result").json()


def _assert_nothing_removed(participants: dict, guest, kratos) -> None:
    assert _participant_ids() == set(participants.values())
    assert _slot_participant_ids() == sorted(participants.values())
    assert [g.id for g in guest_rows()] == [guest.id]
    assert kratos.deleted == []


# ============ 회원 참여자 ============

class TestMemberParticipant:
    def test_removes_participant_and_its_slots_only(self, client, tokens, kratos, meeting_id, guest, participants):
        response = _remove(client, tokens, meeting_id, participants["member"])

        assert response.status_code == 200
        assert response.json() == {"ok": True}
        assert _participant_ids() == {participants["owner"], participants["guest"]}
        assert _slot_participant_ids() == sorted([participants["owner"], participants["guest"]])
        assert [g.id for g in guest_rows()] == [guest.id]
        assert kratos.deleted == []

    def test_result_counts_drop(self, client, tokens, meeting_id, participants):
        before = _result(client, meeting_id)
        assert (before["participant_count"], cell_count(before)) == (3, 3)

        _remove(client, tokens, meeting_id, participants["member"])

        after = _result(client, meeting_id)
        assert (after["participant_count"], cell_count(after)) == (2, 2)

    def test_owner_removes_own_participant(self, client, tokens, meeting_id, participants):
        response = _remove(client, tokens, meeting_id, participants["owner"])

        assert response.status_code == 200
        availability = client.get(f"/v1/meetings/{meeting_id}/availability", headers=tokens.member(MEMBER)).json()
        assert {a["participant"]["id"] for a in availability} == {participants["member"], participants["guest"]}
        assert not any(a["participant"]["is_owner"] for a in availability)

    def test_removed_member_can_participate_again(self, client, tokens, meeting_id, participants):
        _remove(client, tokens, meeting_id, participants["member"])

        response = client.post(
            f"/v1/meetings/{meeting_id}/participate", json={"display_name": "다시"}, headers=tokens.member(MEMBER),
        )

        assert response.status_code == 201
        assert response.json()["id"] != participants["member"]
        assert response.json()["display_name"] == "다시"
        result = _result(client, meeting_id)
        assert (result["participant_count"], cell_count(result)) == (3, 2)


# ============ 게스트 참여자 ============

class TestGuestParticipant:
    def test_discards_guest_with_participant_and_slots(
            self, client, tokens, kratos, meeting_id, guest, participants, guest_events,
    ):
        response = _remove(client, tokens, meeting_id, participants["guest"])

        assert response.status_code == 200
        assert response.json() == {"ok": True}
        assert guest_rows() == []
        assert kratos.deleted == [guest.identity_id]
        assert [(type(e), e.guest_id) for e in guest_events] == [(GuestDiscarded, guest.id)]
        assert _participant_ids() == {participants["owner"], participants["member"]}
        assert _slot_participant_ids() == sorted([participants["owner"], participants["member"]])
        result = _result(client, meeting_id)
        assert (result["participant_count"], cell_count(result)) == (2, 2)

    def test_removed_guest_token_is_refused(self, client, tokens, meeting_id, guest, participants):
        headers = tokens.guest(guest.identity_id)
        assert _remove(client, tokens, meeting_id, participants["guest"]).status_code == 200

        for method, url, body in guest_routes(meeting_id):
            assert call(client, method, url, body, headers).status_code == 403, (method, url)

    def test_other_guests_are_kept(self, client, tokens, kratos, meeting_id, guest, participants):
        other = make_guest(kratos, uuid.UUID(meeting_id), "지수")
        other_participant = participate(client, meeting_id, tokens.guest(other.identity_id))

        _remove(client, tokens, meeting_id, participants["guest"])

        assert [g.id for g in guest_rows()] == [other.id]
        assert kratos.deleted == [guest.identity_id]
        assert other_participant["id"] in _participant_ids()
        assert client.get(f"/v1/meetings/{meeting_id}", headers=tokens.guest(other.identity_id)).status_code == 200

    def test_removed_while_meeting_does_not_accept_guests(self, client, tokens, kratos, meeting_id, guest, participants):
        set_allow_guests(client, tokens, meeting_id, False)

        response = _remove(client, tokens, meeting_id, participants["guest"])

        assert response.status_code == 200
        assert guest_rows() == []
        assert kratos.deleted == [guest.identity_id]
        assert participants["guest"] not in _participant_ids()

    def test_identity_delete_failure_still_removes_guest_row_participant_and_slots(
            self, client, tokens, kratos, meeting_id, guest, participants,
    ):
        kratos.down.add("admin")

        response = _remove(client, tokens, meeting_id, participants["guest"])

        assert response.status_code == 200
        assert guest_rows() == []
        assert _participant_ids() == {participants["owner"], participants["member"]}
        assert _slot_participant_ids() == sorted([participants["owner"], participants["member"]])
        assert kratos.deleted == []
        assert guest.identity_id in kratos.identities
        kratos.down.clear()
        for method, url, body in guest_routes(meeting_id):
            assert call(client, method, url, body, tokens.guest(guest.identity_id)).status_code == 403, (method, url)


# ============ 거절 ============

class TestRefused:
    @pytest.mark.parametrize("target", ["owner", "member", "guest"])
    def test_other_member_gets_same_404_as_missing_meeting(
            self, client, tokens, kratos, meeting_id, guest, participants, target,
    ):
        """MEMBER는 PUBLIC 미팅을 볼 수 있고 참여도 했지만 소유자가 아니다"""
        refused = _remove(client, tokens, meeting_id, participants[target], tokens.member(MEMBER))
        missing = _remove(client, tokens, uuid.uuid4(), participants[target], tokens.member(MEMBER))

        assert refused.status_code == 404
        assert refused.json()["error_type"] == "MeetingNotFoundError"
        assert without_request_values(refused) == without_request_values(missing)
        _assert_nothing_removed(participants, guest, kratos)

    def test_participant_of_other_meeting_is_not_found(self, client, tokens, kratos, meeting_id, guest, participants):
        other_meeting = create_meeting(client, tokens)
        other = participate(client, other_meeting, tokens.member(MEMBER))

        crossed = [
            _remove(client, tokens, meeting_id, other["id"]),
            _remove(client, tokens, other_meeting, participants["member"]),
            _remove(client, tokens, other_meeting, participants["guest"]),
        ]
        unknown = _remove(client, tokens, meeting_id, uuid.uuid4())

        for response in crossed:
            assert response.status_code == 404
            assert response.json()["error_type"] == "MeetingParticipantNotFoundError"
            assert without_request_values(response) == without_request_values(unknown)
        assert other["id"] in _participant_ids()
        assert {participants["member"], participants["guest"]} <= _participant_ids()
        assert [g.id for g in guest_rows()] == [guest.id]
        assert kratos.deleted == []

    @pytest.mark.parametrize("target", ["member", "guest"])
    def test_already_removed_participant_is_not_found(self, client, tokens, kratos, meeting_id, guest, participants, target):
        assert _remove(client, tokens, meeting_id, participants[target]).status_code == 200

        again = _remove(client, tokens, meeting_id, participants[target])

        assert again.status_code == 404
        assert again.json()["error_type"] == "MeetingParticipantNotFoundError"
        assert kratos.deleted == ([guest.identity_id] if target == "guest" else [])

    def test_unknown_or_malformed_ids(self, client, tokens, kratos, meeting_id, guest, participants):
        missing_meeting = _remove(client, tokens, uuid.uuid4(), uuid.uuid4())
        missing_participant = _remove(client, tokens, meeting_id, uuid.uuid4())
        malformed = _remove(client, tokens, meeting_id, "not-a-uuid")

        assert (missing_meeting.status_code, missing_meeting.json()["error_type"]) == (404, "MeetingNotFoundError")
        assert (missing_participant.status_code, missing_participant.json()["error_type"]) == (
            404, "MeetingParticipantNotFoundError",
        )
        assert malformed.status_code == 422
        _assert_nothing_removed(participants, guest, kratos)

    @pytest.mark.parametrize("target", ["owner", "member", "guest"])
    def test_guest_token_is_refused(self, client, tokens, kratos, meeting_id, guest, participants, target):
        response = _remove(client, tokens, meeting_id, participants[target], tokens.guest(guest.identity_id))

        assert response.status_code == 403
        _assert_nothing_removed(participants, guest, kratos)

    def test_without_token_is_401(self, client, tokens, kratos, meeting_id, guest, participants):
        response = _remove(client, tokens, meeting_id, participants["member"], headers={})

        assert response.status_code == 401
        _assert_nothing_removed(participants, guest, kratos)

    def test_dormant_owner_is_refused_until_cancelled(self, client, tokens, kratos, meeting_id, guest, participants):
        assert client.post("/v1/users/me/deletion", headers=tokens.member(OWNER)).status_code == 200

        response = _remove(client, tokens, meeting_id, participants["guest"])

        assert response.status_code == 423
        _assert_nothing_removed(participants, guest, kratos)
        assert client.delete("/v1/users/me/deletion", headers=tokens.member(OWNER)).status_code == 200
        assert _remove(client, tokens, meeting_id, participants["guest"]).status_code == 200

    def test_owner_consent_is_required(self, client, tokens, kratos, meeting_id, guest, participants, monkeypatch):
        monkeypatch.setattr(app_config.settings, "CONSENT_ENFORCED", True)

        response = _remove(client, tokens, meeting_id, participants["member"])

        assert response.status_code == 428
        _assert_nothing_removed(participants, guest, kratos)
