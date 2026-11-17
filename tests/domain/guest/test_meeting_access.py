"""미팅 경로의 로그인하지 않은 방문자·게스트 접근 (app/api/v1/meetings.py의 shared_router)

- 로그인하지 않은 방문자: PUBLIC 미팅의 정보와 결과 그리드를 본다. 참여자 이름과 가능 시간, 참여·가능 시간 설정은 401.
  PUBLIC이 아니거나 소유자가 휴면 계정인 미팅은 없는 미팅과 같은 404
- 게스트: 자기 미팅이 OPEN일 때 정보·결과·참여자별 가능 시간을 본다. 다른 미팅이거나 OPEN이 아니면 403
- 게스트와 방문자의 응답에는 회원의 sub가 없다
"""
import uuid
from datetime import datetime

import pytest

import app.core.config as app_config
from app.domain.meeting import guest_host
from tests.domain.guest.helpers import guest_rows, make_guest
from tests.domain.guest.meeting_helpers import (
    MEETING,
    MEMBER,
    OWNER,
    SLOT,
    SLOT_CELL_START,
    call,
    cell_count,
    create_meeting,
    guest_routes,
    participate,
    set_allow_guests,
    set_level,
    set_slots,
    without_request_values,
)


@pytest.fixture
def client(guest_client, meeting_host):
    return guest_client


@pytest.fixture
def meeting_id(client, tokens) -> str:
    """PUBLIC이고 게스트를 허용한 미팅. 회원 MEMBER가 참여해 가능 시간 하나를 넣었다"""
    meeting_id = create_meeting(client, tokens)
    member = participate(client, meeting_id, tokens.member(MEMBER), name="회원")
    assert set_slots(client, meeting_id, member["id"], tokens.member(MEMBER)).status_code == 200
    return meeting_id


@pytest.fixture
def guest(kratos, meeting_id):
    return make_guest(kratos, uuid.UUID(meeting_id), "민수")


def _no_member_subs(text: str) -> None:
    assert OWNER not in text
    assert MEMBER not in text


def _go_dormant(client, tokens, sub: str = OWNER) -> None:
    assert client.post("/v1/users/me/deletion", headers=tokens.member(sub)).status_code == 200


def _come_back(client, tokens, sub: str = OWNER) -> None:
    assert client.delete("/v1/users/me/deletion", headers=tokens.member(sub)).status_code == 200


# ============ 로그인하지 않은 방문자 ============

class TestAnonymous:
    def test_reads_public_meeting_without_owner(self, client, meeting_id):
        response = client.get(f"/v1/meetings/{meeting_id}")

        assert response.status_code == 200
        body = response.json()
        for field in ("title", "description", "start_date", "end_date", "timezone", "mode",
                      "start_time", "end_time", "time_slot_minutes"):
            assert body[field] == MEETING[field]
        assert body["allow_guests"] is True
        assert body["owner_id"] is None
        assert body["visibility_level"] == "public"
        _no_member_subs(response.text)

    def test_reads_result_counts_without_names(self, client, meeting_id):
        response = client.get(f"/v1/meetings/{meeting_id}/result")

        assert response.status_code == 200
        assert cell_count(response.json()) == 1
        assert response.json()["meeting"]["owner_id"] is None
        _no_member_subs(response.text)
        assert "회원" not in response.text

    @pytest.mark.parametrize("existing", [True, False])
    def test_participants_and_writes_need_login(self, client, meeting_id, existing):
        target = meeting_id if existing else str(uuid.uuid4())
        for method, url, body in guest_routes(target)[2:]:
            response = call(client, method, url, body)
            assert response.status_code == 401, (method, url)

    def test_login_answers_do_not_differ_between_public_and_missing(self, client, meeting_id):
        for (method, url, body), (_, missing_url, _) in zip(
                guest_routes(meeting_id)[2:], guest_routes(str(uuid.uuid4()))[2:],
        ):
            assert without_request_values(call(client, method, url, body)) == without_request_values(
                call(client, method, missing_url, body)
            )

    @pytest.mark.parametrize("level", ["private", "friends", "selected", "allowed_emails", None])
    @pytest.mark.parametrize("path", ["", "/result"])
    def test_non_public_meeting_is_same_as_missing(self, client, tokens, meeting_id, level, path):
        set_level(client, tokens, meeting_id, level)

        hidden = client.get(f"/v1/meetings/{meeting_id}{path}")
        missing = client.get(f"/v1/meetings/{uuid.uuid4()}{path}")

        assert hidden.status_code == 404
        assert without_request_values(hidden) == without_request_values(missing)

    @pytest.mark.parametrize("path", ["", "/result"])
    def test_dormant_owner_meeting_is_same_as_missing_until_cancelled(self, client, tokens, meeting_id, path):
        _go_dormant(client, tokens)

        hidden = client.get(f"/v1/meetings/{meeting_id}{path}")
        assert without_request_values(hidden) == without_request_values(
            client.get(f"/v1/meetings/{uuid.uuid4()}{path}")
        )

        _come_back(client, tokens)
        assert client.get(f"/v1/meetings/{meeting_id}{path}").status_code == 200

    def test_public_meeting_without_guests_is_visible(self, client, tokens, meeting_id):
        set_allow_guests(client, tokens, meeting_id, False)

        response = client.get(f"/v1/meetings/{meeting_id}")

        assert response.status_code == 200
        assert response.json()["allow_guests"] is False

    def test_visible_when_guests_are_off(self, client, meeting_id, guest_off):
        guest_off()

        assert client.get(f"/v1/meetings/{meeting_id}").status_code == 200
        assert client.get(f"/v1/meetings/{meeting_id}/result").status_code == 200

    @pytest.mark.parametrize("path", ["", "/result"])
    def test_invalid_token_is_401(self, client, meeting_id, path):
        response = client.get(f"/v1/meetings/{meeting_id}{path}", headers={"Authorization": "Bearer not-a-token"})

        assert response.status_code == 401


# ============ 회원 (바뀌지 않는다) ============

class TestMember:
    def test_member_reads_owner_and_user_ids(self, client, tokens, meeting_id):
        meeting = client.get(f"/v1/meetings/{meeting_id}", headers=tokens.member(MEMBER)).json()
        availability = client.get(f"/v1/meetings/{meeting_id}/availability", headers=tokens.member(OWNER)).json()

        assert meeting["owner_id"] == OWNER
        assert [a["participant"]["user_id"] for a in availability] == [MEMBER]

    def test_member_without_access_gets_404(self, client, tokens, meeting_id):
        set_level(client, tokens, meeting_id, "private")

        for method, url, body in guest_routes(meeting_id):
            assert call(client, method, url, body, tokens.member(MEMBER)).status_code == 404, (method, url)

    def test_member_consent_is_still_required(self, client, tokens, meeting_id, monkeypatch):
        monkeypatch.setattr(app_config.settings, "CONSENT_ENFORCED", True)

        response = client.get(f"/v1/meetings/{meeting_id}", headers=tokens.member(MEMBER))

        assert response.status_code == 428

    def test_dormant_member_is_refused(self, client, tokens, meeting_id):
        _go_dormant(client, tokens, MEMBER)

        response = client.get(f"/v1/meetings/{meeting_id}", headers=tokens.member(MEMBER))

        assert response.status_code == 423


# ============ 게스트 ============

class TestGuest:
    def test_reads_meeting_result_and_availability(self, client, tokens, meeting_id, guest):
        headers = tokens.guest(guest.identity_id)

        meeting = client.get(f"/v1/meetings/{meeting_id}", headers=headers)
        result = client.get(f"/v1/meetings/{meeting_id}/result", headers=headers)
        availability = client.get(f"/v1/meetings/{meeting_id}/availability", headers=headers)

        assert meeting.status_code == result.status_code == availability.status_code == 200
        assert meeting.json()["owner_id"] is None
        assert result.json()["meeting"]["owner_id"] is None
        assert cell_count(result.json()) == 1
        assert [a["participant"]["display_name"] for a in availability.json()] == ["회원"]
        assert [a["participant"]["user_id"] for a in availability.json()] == [None]
        assert len(availability.json()[0]["time_slots"]) == 1
        for response in (meeting, result, availability):
            _no_member_subs(response.text)

    def test_guest_of_other_meeting_is_refused(self, client, tokens, kratos, meeting_id):
        other = make_guest(kratos, uuid.UUID(create_meeting(client, tokens, owner="owner-2")), "지수")

        for method, url, body in guest_routes(meeting_id):
            response = call(client, method, url, body, tokens.guest(other.identity_id))
            assert response.status_code == 403, (method, url)

    def test_refused_on_missing_meeting_id(self, client, tokens, guest):
        for method, url, body in guest_routes(str(uuid.uuid4())):
            assert call(client, method, url, body, tokens.guest(guest.identity_id)).status_code == 403

    def _assert_refused_and_kept(self, client, tokens, meeting_id, guest):
        for method, url, body in guest_routes(meeting_id):
            response = call(client, method, url, body, tokens.guest(guest.identity_id))
            assert response.status_code == 403, (method, url)
        assert [g.id for g in guest_rows()] == [guest.id]

    def test_refused_while_guests_turned_off(self, client, tokens, meeting_id, guest):
        set_allow_guests(client, tokens, meeting_id, False)
        self._assert_refused_and_kept(client, tokens, meeting_id, guest)

        set_allow_guests(client, tokens, meeting_id, True)
        assert client.get(f"/v1/meetings/{meeting_id}", headers=tokens.guest(guest.identity_id)).status_code == 200

    @pytest.mark.parametrize("level", ["private", "friends", "allowed_emails", None])
    def test_refused_while_not_public(self, client, tokens, meeting_id, guest, level):
        set_level(client, tokens, meeting_id, level)
        self._assert_refused_and_kept(client, tokens, meeting_id, guest)

        set_level(client, tokens, meeting_id, "public")
        assert client.get(f"/v1/meetings/{meeting_id}", headers=tokens.guest(guest.identity_id)).status_code == 200

    def test_refused_while_owner_dormant(self, client, tokens, meeting_id, guest):
        _go_dormant(client, tokens)
        self._assert_refused_and_kept(client, tokens, meeting_id, guest)

        _come_back(client, tokens)
        assert client.get(f"/v1/meetings/{meeting_id}", headers=tokens.guest(guest.identity_id)).status_code == 200

    def test_deleted_guest_token_is_refused(self, client, tokens, meeting_id, guest):
        headers = tokens.guest(guest.identity_id)
        assert client.delete("/v1/guests/me", headers={**headers, "X-Turnstile-Token": "t"}).status_code == 204

        for method, url, body in guest_routes(meeting_id):
            assert call(client, method, url, body, headers).status_code == 403, (method, url)

    def test_open_until_period_end_then_refused_and_discarded(self, client, tokens, kratos, meeting_id, guest, monkeypatch):
        """end_date 2099-03-06(UTC)의 게스트 기간은 2099-04-06 00:00 UTC 전까지"""
        headers = tokens.guest(guest.identity_id)
        url = f"/v1/meetings/{meeting_id}"

        monkeypatch.setattr(guest_host, "utc_now_naive", lambda: datetime(2099, 4, 5, 23, 59, 59, 999999))
        assert client.get(url, headers=headers).status_code == 200

        monkeypatch.setattr(guest_host, "utc_now_naive", lambda: datetime(2099, 4, 6))
        assert client.get(url, headers=headers).status_code == 403
        assert guest_rows() == []
        assert guest.identity_id in kratos.deleted
        assert client.get(url).status_code == 200  # 방문자는 기간과 상관없다

    def test_refused_when_guests_are_off(self, client, tokens, meeting_id, guest, guest_off):
        guest_off()

        for method, url, body in guest_routes(meeting_id):
            assert call(client, method, url, body, tokens.guest(guest.identity_id)).status_code == 403

    def test_consent_is_required(self, client, tokens, meeting_id, guest, monkeypatch):
        monkeypatch.setattr(app_config.settings, "CONSENT_ENFORCED", True)

        response = client.get(f"/v1/meetings/{meeting_id}", headers=tokens.guest(guest.identity_id))

        assert response.status_code == 428

    def test_guest_cannot_use_member_meeting_routes(self, client, tokens, meeting_id, guest):
        headers = tokens.guest(guest.identity_id)

        assert client.get("/v1/meetings", headers=headers).status_code == 403
        assert client.post("/v1/meetings", json=MEETING, headers=headers).status_code == 403
        assert client.patch(f"/v1/meetings/{meeting_id}", json={"title": "x"}, headers=headers).status_code == 403
        assert client.delete(f"/v1/meetings/{meeting_id}", headers=headers).status_code == 403
        assert client.get(f"/v1/meetings/{meeting_id}", headers=tokens.member(OWNER)).json()["title"] == MEETING["title"]


# ============ 참여자 수와 참여자 역할 ============

class TestParticipantCountAndRoles:
    @pytest.fixture
    def participants(self, client, tokens, meeting_id, guest) -> dict:
        """MEMBER(가능 시간 있음), OWNER(가능 시간 없음), 게스트(가능 시간 있음), 휴면이 된 회원"""
        owner = participate(client, meeting_id, tokens.member(OWNER), name="방장")
        guest_participant = participate(client, meeting_id, tokens.guest(guest.identity_id))
        set_slots(client, meeting_id, guest_participant["id"], tokens.guest(guest.identity_id))
        participate(client, meeting_id, tokens.member("member-dormant"), name="휴면")
        _go_dormant(client, tokens, "member-dormant")
        return {"owner": owner["id"], "guest": guest_participant["id"]}

    def test_count_is_same_for_anonymous_guest_and_member(self, client, tokens, meeting_id, guest, participants):
        anonymous = client.get(f"/v1/meetings/{meeting_id}/result").json()
        as_guest = client.get(f"/v1/meetings/{meeting_id}/result", headers=tokens.guest(guest.identity_id)).json()
        as_member = client.get(f"/v1/meetings/{meeting_id}/result", headers=tokens.member(MEMBER)).json()

        assert anonymous["participant_count"] == as_guest["participant_count"] == as_member["participant_count"] == 3
        assert cell_count(anonymous) == cell_count(as_member) == 2

    def test_count_follows_dormant_member_coming_back(self, client, tokens, meeting_id, participants):
        _come_back(client, tokens, "member-dormant")

        assert client.get(f"/v1/meetings/{meeting_id}/result").json()["participant_count"] == 4

    def test_count_with_timezone_query(self, client, meeting_id, participants):
        response = client.get(f"/v1/meetings/{meeting_id}/result", params={"timezone": "Asia/Seoul"})

        assert response.json()["participant_count"] == 3

    def test_unavailable_count_is_same_for_anonymous_guest_and_member(
            self, client, tokens, meeting_id, guest, participants,
    ):
        response = set_slots(
            client, meeting_id, participants["owner"], tokens.member(OWNER), slots=[{**SLOT, "kind": "unavailable"}],
        )
        assert response.status_code == 200, response.text

        for headers in ({}, tokens.guest(guest.identity_id), tokens.member(MEMBER)):
            result = client.get(f"/v1/meetings/{meeting_id}/result", headers=headers).json()
            cell = next(c for c in result["availability_grid"] if c["start_time"] == SLOT_CELL_START)
            assert (cell["count"], cell["unavailable_count"]) == (2, 1)

    def test_anonymous_result_has_no_participant_ids(self, client, meeting_id, participants):
        text = client.get(f"/v1/meetings/{meeting_id}/result").text

        assert participants["owner"] not in text
        assert participants["guest"] not in text
        assert "방장" not in text and "민수" not in text

    @pytest.mark.parametrize("viewer", ["member", "guest"])
    def test_roles_in_availability(self, client, tokens, meeting_id, guest, participants, viewer):
        headers = tokens.member(MEMBER) if viewer == "member" else tokens.guest(guest.identity_id)

        availability = client.get(f"/v1/meetings/{meeting_id}/availability", headers=headers).json()

        roles = {a["participant"]["display_name"]: (a["participant"]["is_owner"], a["participant"]["is_guest"])
                 for a in availability}
        assert roles == {"회원": (False, False), "방장": (True, False), "민수": (False, True)}
        user_ids = {a["participant"]["display_name"]: a["participant"]["user_id"] for a in availability}
        if viewer == "member":
            assert user_ids == {"회원": MEMBER, "방장": OWNER, "민수": None}
        else:
            assert set(user_ids.values()) == {None}

    def test_roles_in_participate_response(self, client, tokens, meeting_id, guest):
        as_owner = participate(client, meeting_id, tokens.member(OWNER), name="방장")
        as_guest = participate(client, meeting_id, tokens.guest(guest.identity_id))
        as_member = participate(client, meeting_id, tokens.member(MEMBER), name="회원")

        assert (as_owner["is_owner"], as_owner["is_guest"]) == (True, False)
        assert (as_guest["is_owner"], as_guest["is_guest"]) == (False, True)
        assert (as_member["is_owner"], as_member["is_guest"]) == (False, False)
