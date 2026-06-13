"""
Users / 친구코드 친추 E2E 테스트

- GET /v1/users/me: 본인 프로필 get-or-create, friend_code 공유, email 미노출
- 친구코드 기반 친추: 코드로 친추 → 받은 요청에 발신자 display_name/avatar 표시
"""


class TestUsersMe:
    def test_get_my_profile_creates_and_returns(self, e2e_client):
        """GET /users/me는 프로필을 생성하고 표시정보+friend_code를 반환"""
        r = e2e_client.get("/v1/users/me")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == "test-user-id"
        assert data["display_name"] == "Test User"  # mock 사용자 name 클레임
        assert data["friend_code"]

    def test_email_never_exposed(self, e2e_client):
        """email은 프로필 응답에 절대 포함되지 않는다"""
        data = e2e_client.get("/v1/users/me").json()
        assert "email" not in data

    def test_friend_code_is_stable(self, e2e_client):
        """반복 조회해도 friend_code는 동일(idempotent)"""
        c1 = e2e_client.get("/v1/users/me").json()["friend_code"]
        c2 = e2e_client.get("/v1/users/me").json()["friend_code"]
        assert c1 == c2


class TestFriendCodeFlow:
    def test_add_friend_by_code_then_received_shows_display_name(self, multi_user_e2e):
        """B의 코드로 A가 친추 → B의 받은 요청에 A의 display_name/avatar 표시"""
        a = multi_user_e2e.as_user("user-a", name="Alice")
        b = multi_user_e2e.as_user("user-b", name="Bob")

        b_code = b.get("/v1/users/me").json()["friend_code"]

        sent = a.post("/v1/friends/requests", json={"identifier": b_code})
        assert sent.status_code == 201, sent.json()

        received = b.get("/v1/friends/requests/received").json()
        assert len(received) == 1
        item = received[0]
        assert item["requester_id"] == multi_user_e2e.get_user("user-a").sub
        assert item["requester_display_name"] == "Alice"
        assert "requester_avatar_url" in item  # 키 존재(값은 None일 수 있음)

    def test_invalid_friend_code_returns_404(self, multi_user_e2e):
        a = multi_user_e2e.as_user("user-a")
        r = a.post("/v1/friends/requests", json={"identifier": "does-not-exist"})
        assert r.status_code == 404

    def test_self_friend_code_returns_400(self, multi_user_e2e):
        a = multi_user_e2e.as_user("user-a")
        own_code = a.get("/v1/users/me").json()["friend_code"]
        r = a.post("/v1/friends/requests", json={"identifier": own_code})
        assert r.status_code == 400

    def test_accept_then_friend_list_has_display_name(self, multi_user_e2e):
        a = multi_user_e2e.as_user("user-a", name="Alice")
        b = multi_user_e2e.as_user("user-b", name="Bob")

        b_code = b.get("/v1/users/me").json()["friend_code"]
        friendship_id = a.post("/v1/friends/requests", json={"identifier": b_code}).json()["id"]

        accept = b.post(f"/v1/friends/requests/{friendship_id}/accept")
        assert accept.status_code == 200

        friends_a = a.get("/v1/friends").json()
        assert len(friends_a) == 1
        assert friends_a[0]["user_id"] == multi_user_e2e.get_user("user-b").sub
        assert friends_a[0]["display_name"] == "Bob"

    def test_blocked_user_cannot_friend_by_code(self, multi_user_e2e):
        """차단 관계면 코드를 알아도 친추가 막힌다"""
        a = multi_user_e2e.as_user("user-a")
        b = multi_user_e2e.as_user("user-b")

        a_code = a.get("/v1/users/me").json()["friend_code"]
        b_id = multi_user_e2e.get_user("user-b").sub

        # A가 B를 차단
        assert a.post(f"/v1/friends/block/{b_id}").status_code == 200

        # B가 A의 코드로 친추 시도 → 차단으로 거절
        r = b.post("/v1/friends/requests", json={"identifier": a_code})
        assert r.status_code in (400, 403, 409)


class TestEmailFriendRequest:
    """이메일 경로 — 항상 균일 202(존재/자기자신/중복/차단 비노출)"""

    def test_add_by_email_creates_request(self, multi_user_e2e):
        a = multi_user_e2e.as_user("user-a", name="Alice")
        b = multi_user_e2e.as_user("user-b", name="Bob")
        b.get("/v1/users/me")  # B 동기화(email_hash 인덱싱)
        b_email = multi_user_e2e.get_user("user-b").email

        r = a.post("/v1/friends/requests", json={"identifier": b_email})
        assert r.status_code == 202
        assert r.json() == {"ok": True}

        received = b.get("/v1/friends/requests/received").json()
        assert len(received) == 1
        assert received[0]["requester_display_name"] == "Alice"

    def test_unknown_email_uniform_202_no_request(self, multi_user_e2e):
        a = multi_user_e2e.as_user("user-a")
        r = a.post("/v1/friends/requests", json={"identifier": "nobody@nowhere.example"})
        assert r.status_code == 202
        assert r.json() == {"ok": True}
        assert a.get("/v1/friends/requests/sent").json() == []

    def test_self_email_uniform_202_no_request(self, multi_user_e2e):
        a = multi_user_e2e.as_user("user-a")
        a_email = multi_user_e2e.get_user("user-a").email
        r = a.post("/v1/friends/requests", json={"identifier": a_email})
        assert r.status_code == 202  # 자기자신도 균일 202
        assert a.get("/v1/friends/requests/sent").json() == []  # 요청 미생성

    def test_duplicate_email_uniform_202_single_request(self, multi_user_e2e):
        a = multi_user_e2e.as_user("user-a")
        b = multi_user_e2e.as_user("user-b")
        b.get("/v1/users/me")
        b_email = multi_user_e2e.get_user("user-b").email

        first = a.post("/v1/friends/requests", json={"identifier": b_email})
        second = a.post("/v1/friends/requests", json={"identifier": b_email})
        assert first.status_code == 202
        assert second.status_code == 202  # 중복도 균일 202(409 비노출)
        assert len(b.get("/v1/friends/requests/received").json()) == 1

    def test_unverified_email_not_findable(self, multi_user_e2e):
        """email_verified=false면 이메일로 안 찾힘(균일 202, 요청 미생성)"""
        a = multi_user_e2e.as_user("user-a")
        # email_verified=False인 사용자
        b = multi_user_e2e.as_user("user-b", email="user-b@example.com")
        multi_user_e2e.get_user("user-b").email_verified = False
        b.get("/v1/users/me")

        r = a.post("/v1/friends/requests", json={"identifier": "user-b@example.com"})
        assert r.status_code == 202
        assert b.get("/v1/friends/requests/received").json() == []


class TestGlobalProfileSync:
    """비소셜(인증) 엔드포인트 호출만으로도 프로필·email_hash가 동기화됨"""

    def test_sync_on_non_social_endpoint_enables_email_add(self, multi_user_e2e):
        a = multi_user_e2e.as_user("user-a", name="Alice")
        b = multi_user_e2e.as_user("user-b", name="Bob")

        # A는 소셜 엔드포인트(/users/me·/friends)를 전혀 안 거치고 schedules만 호출
        resp = a.get(
            "/v1/schedules",
            params={"start_date": "2024-01-01T00:00:00Z", "end_date": "2024-01-01T23:59:59Z"},
        )
        assert resp.status_code == 200

        # 그래도 B가 A를 이메일로 추가 가능(전역 동기화로 A의 email_hash 확보됨)
        a_email = multi_user_e2e.get_user("user-a").email
        r = b.post("/v1/friends/requests", json={"identifier": a_email})
        assert r.status_code == 202

        received_a = a.get("/v1/friends/requests/received").json()
        assert len(received_a) == 1
        assert received_a[0]["requester_display_name"] == "Bob"
