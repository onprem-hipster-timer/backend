"""
휴면 계정(탈퇴 신청 후 파기 전)은 다른 사용자에게 보이지 않는다

- 공유 일정·Todo·타이머·미팅: 목록(scope=shared)과 단건 조회에서 빠진다
- 친구 목록·친구 ID·받은/보낸 요청에서 빠진다. 휴면 계정이 보낸 요청은 수락할 수 없다
- 친구코드는 404, 이메일 요청은 202이지만 요청이 생기지 않는다
- 미팅 /participants·/availability·/result에서 휴면 참여자가 빠진다
- 휴면 소유자의 타이머 이벤트를 다른 사용자에게 보내지 않고, 휴면 사용자에게도 보내지 않는다
- 신청을 취소하면 다시 보인다
"""
from uuid import uuid4

import pytest

from app.domain.friend.service import FriendService
from app.domain.user.service import UserProfileService
from app.domain.visibility.enums import ResourceType, VisibilityLevel
from app.domain.visibility.service import VisibilityService
from tests.conftest import TimerCommands, make_user

DAY = {"start_date": "2024-01-01T00:00:00Z", "end_date": "2024-01-01T23:59:59Z"}


def _code(client) -> str:
    return client.get("/v1/users/me").json()["friend_code"]


def _befriend(requester, addressee) -> None:
    assert requester.post("/v1/friends/requests", json={"friend_code": _code(addressee)}).status_code == 201
    request_id = addressee.get("/v1/friends/requests/received").json()[-1]["id"]
    assert addressee.post(f"/v1/friends/requests/{request_id}/accept").status_code == 200


def _go_dormant(client) -> None:
    assert client.post("/v1/users/me/deletion").status_code == 200


def _come_back(client) -> None:
    assert client.delete("/v1/users/me/deletion").status_code == 200


def _share(client, resource: str, resource_id: str, level: str = "friends") -> None:
    assert client.put(f"/v1/visibility/{resource}/{resource_id}", json={"level": level}).status_code == 200


def _make_schedule(client) -> str:
    return client.post(
        "/v1/schedules",
        json={"title": "공유 일정", "start_time": "2024-01-01T10:00:00Z", "end_time": "2024-01-01T12:00:00Z"},
    ).json()["id"]


def _make_todo(client) -> str:
    group_id = client.post("/v1/todos/groups", json={"name": "업무", "color": "#FF5733"}).json()["id"]
    return client.post("/v1/todos", json={"title": "공유 Todo", "todo_group_id": group_id}).json()["id"]


def _make_timer(client) -> str:
    return TimerCommands(client).create_timer(title="공유 타이머", allocated_duration=1800)["id"]


def _make_meeting(client) -> str:
    return client.post(
        "/v1/meetings",
        json={
            "title": "회의",
            "start_date": "2024-02-01",
            "end_date": "2024-02-07",
            "available_days": [0, 2, 4],
            "start_time": "09:00:00",
            "end_time": "18:00:00",
            "time_slot_minutes": 30,
        },
    ).json()["id"]


def _participate(client, meeting_id: str, name: str) -> str:
    participant_id = client.post(
        f"/v1/meetings/{meeting_id}/participate", json={"display_name": name}
    ).json()["id"]
    r = client.put(
        f"/v1/meetings/{meeting_id}/availability",
        params={"participant_id": participant_id},
        json=[{"slot_date": "2024-02-02", "start_time": "09:00:00", "end_time": "10:00:00"}],
    )
    assert r.status_code == 200
    return participant_id


@pytest.fixture
def ab(multi_user_e2e):
    """친구인 a(곧 휴면)와 b"""
    a = multi_user_e2e.as_user("user-a")
    b = multi_user_e2e.as_user("user-b")
    _befriend(a, b)
    return a, b


class TestSharedResources:
    @pytest.mark.parametrize(
        ("resource", "make", "list_path", "params"),
        [
            ("schedule", _make_schedule, "/v1/schedules", DAY),
            ("todo", _make_todo, "/v1/todos", {}),
            ("timer", _make_timer, "/v1/timers", {}),
        ],
    )
    @pytest.mark.parametrize("level", ["friends", "public"])
    def test_hidden_from_list_and_single_get(self, ab, resource, make, list_path, params, level):
        a, b = ab
        resource_id = make(a)
        _share(a, resource, resource_id, level)

        def shared_ids():
            r = b.get(list_path, params={**params, "scope": "shared"})
            assert r.status_code == 200
            return [item["id"] for item in r.json()]

        assert resource_id in shared_ids()
        assert b.get(f"{list_path}/{resource_id}").status_code == 200

        _go_dormant(a)
        assert resource_id not in shared_ids()
        assert b.get(f"{list_path}/{resource_id}").status_code == 403

        _come_back(a)
        assert resource_id in shared_ids()
        assert b.get(f"{list_path}/{resource_id}").status_code == 200

    def test_shared_schedule_in_scope_all(self, ab):
        a, b = ab
        schedule_id = _make_schedule(a)
        _share(a, "schedule", schedule_id)
        _go_dormant(a)

        r = b.get("/v1/schedules", params={**DAY, "scope": "all"})

        assert schedule_id not in [item["id"] for item in r.json()]

    def test_allowed_email_share_hidden(self, multi_user_e2e):
        a = multi_user_e2e.as_user("user-a")
        b = multi_user_e2e.as_user("user-b", email="b@company.com")
        schedule_id = _make_schedule(a)
        a.put(f"/v1/visibility/schedule/{schedule_id}", json={"level": "allowed_emails", "allowed_emails": ["b@company.com"]})
        assert b.get(f"/v1/schedules/{schedule_id}").status_code == 200

        _go_dormant(a)

        assert b.get(f"/v1/schedules/{schedule_id}").status_code == 403


class TestFriends:
    def test_hidden_from_friend_list_and_ids(self, ab, multi_user_e2e):
        a, b = ab
        a_sub = multi_user_e2e.get_user("user-a").sub
        assert a_sub in b.get("/v1/friends/ids").json()

        _go_dormant(a)

        assert b.get("/v1/friends").json() == []
        assert b.get("/v1/friends/ids").json() == []

        _come_back(a)
        assert [f["user_id"] for f in b.get("/v1/friends").json()] == [a_sub]

    def test_pending_requests_hidden_both_directions(self, multi_user_e2e):
        a = multi_user_e2e.as_user("user-a")
        b = multi_user_e2e.as_user("user-b")
        c = multi_user_e2e.as_user("user-c")
        a.post("/v1/friends/requests", json={"friend_code": _code(b)})
        c.post("/v1/friends/requests", json={"friend_code": _code(a)})
        assert len(b.get("/v1/friends/requests/received").json()) == 1
        assert len(c.get("/v1/friends/requests/sent").json()) == 1

        _go_dormant(a)

        assert b.get("/v1/friends/requests/received").json() == []
        assert c.get("/v1/friends/requests/sent").json() == []

        _come_back(a)
        assert len(b.get("/v1/friends/requests/received").json()) == 1
        assert len(c.get("/v1/friends/requests/sent").json()) == 1

    def test_cannot_accept_request_from_dormant_user(self, multi_user_e2e):
        a = multi_user_e2e.as_user("user-a")
        b = multi_user_e2e.as_user("user-b")
        a.post("/v1/friends/requests", json={"friend_code": _code(b)})
        request_id = b.get("/v1/friends/requests/received").json()[0]["id"]

        _go_dormant(a)

        assert b.post(f"/v1/friends/requests/{request_id}/accept").status_code == 404

    def test_friend_code_not_found(self, multi_user_e2e):
        a = multi_user_e2e.as_user("user-a")
        b = multi_user_e2e.as_user("user-b")
        a_code = _code(a)
        _go_dormant(a)

        r = b.post("/v1/friends/requests", json={"friend_code": a_code})

        assert r.status_code == 404
        assert r.json() == b.post("/v1/friends/requests", json={"friend_code": "no-such-code"}).json() | {
            "error_id": r.json()["error_id"], "timestamp": r.json()["timestamp"],
        }

    def test_email_request_is_uniform_and_creates_nothing(self, multi_user_e2e):
        a = multi_user_e2e.as_user("user-a", email="a@example.com")
        b = multi_user_e2e.as_user("user-b")
        a.get("/v1/users/me")
        _go_dormant(a)

        r = b.post("/v1/friends/requests", json={"email": "a@example.com"})

        assert r.status_code == 202
        assert r.json() == {"ok": True}
        assert b.get("/v1/friends/requests/sent").json() == []
        _come_back(a)
        assert a.get("/v1/friends/requests/received").json() == []


class TestMeetings:
    def test_owned_meeting_inaccessible(self, ab):
        a, b = ab
        meeting_id = _make_meeting(a)
        _share(a, "meeting", meeting_id, "public")
        assert b.get(f"/v1/meetings/{meeting_id}").status_code == 200

        _go_dormant(a)

        for path in ("", "/availability", "/result"):
            assert b.get(f"/v1/meetings/{meeting_id}{path}").status_code == 403
        assert b.post(f"/v1/meetings/{meeting_id}/participate", json={"display_name": "b"}).status_code == 403

    def test_dormant_participant_excluded(self, multi_user_e2e):
        owner = multi_user_e2e.as_user("owner")
        a = multi_user_e2e.as_user("user-a")
        b = multi_user_e2e.as_user("user-b")
        meeting_id = _make_meeting(owner)
        _share(owner, "meeting", meeting_id, "public")
        _participate(a, meeting_id, "A")
        b_participant = _participate(b, meeting_id, "B")

        def nine_oclock_count():
            grid = owner.get(f"/v1/meetings/{meeting_id}/result").json()["availability_grid"]
            day = next(g for g in grid if g["date"] == "2024-02-02")
            return next(s["count"] for s in day["slots"] if s["time"] == "09:00")

        assert nine_oclock_count() == 2

        _go_dormant(a)

        availability = owner.get(f"/v1/meetings/{meeting_id}/availability").json()
        assert [item["participant"]["id"] for item in availability] == [b_participant]
        assert nine_oclock_count() == 1

        _come_back(a)
        assert nine_oclock_count() == 2
        assert len(owner.get(f"/v1/meetings/{meeting_id}/availability").json()) == 2


class TestRealtimeRecipients:
    OWNER = make_user("owner")
    FRIEND = make_user("friend")

    @pytest.fixture
    def shared_timer(self, test_session):
        request = FriendService(test_session, self.OWNER).send_friend_request(self.FRIEND.sub)
        FriendService(test_session, self.FRIEND).accept_friend_request(request.id)
        for user in (self.OWNER, self.FRIEND):
            UserProfileService(test_session, user).sync_from_current_user()
        timer_id = uuid4()
        VisibilityService(test_session, self.OWNER).set_visibility(ResourceType.TIMER, timer_id, VisibilityLevel.FRIENDS)
        test_session.flush()
        return timer_id

    def _recipients(self, session, timer_id):
        return VisibilityService(session, self.OWNER).get_realtime_recipients(ResourceType.TIMER, timer_id, self.OWNER.sub)

    def test_friend_receives_when_both_active(self, test_session, shared_timer):
        assert self._recipients(test_session, shared_timer) == {"friend"}

    def test_dormant_owner_has_no_recipients(self, test_session, shared_timer):
        UserProfileService(test_session, self.OWNER).request_deletion()

        assert self._recipients(test_session, shared_timer) == set()

    def test_dormant_friend_is_not_a_recipient(self, test_session, shared_timer):
        UserProfileService(test_session, self.FRIEND).request_deletion()

        assert self._recipients(test_session, shared_timer) == set()

    def test_timer_event_reaches_only_owner_when_dormant(self, multi_user_e2e, after_commit_items):
        a = multi_user_e2e.as_user("user-a")
        b = multi_user_e2e.as_user("user-b")
        _befriend(a, b)
        timer_id = _make_timer(a)
        _share(a, "timer", timer_id)
        after_commit_items.clear()
        TimerCommands(a).pause_timer(timer_id)
        assert after_commit_items[-1]["users"] == {"user-a", "user-b"}

        _go_dormant(b)
        after_commit_items.clear()
        TimerCommands(a).resume_timer(timer_id)

        assert after_commit_items[-1]["users"] == {"user-a"}
