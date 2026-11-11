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

        sent = a.post("/v1/friends/requests", json={"friend_code": b_code})
        assert sent.status_code == 201, sent.json()

        received = b.get("/v1/friends/requests/received").json()
        assert len(received) == 1
        item = received[0]
        assert item["requester_id"] == multi_user_e2e.get_user("user-a").sub
        assert item["requester_display_name"] == "Alice"
        assert "requester_avatar_url" in item  # 키 존재(값은 None일 수 있음)

    def test_invalid_friend_code_returns_404(self, multi_user_e2e):
        a = multi_user_e2e.as_user("user-a")
        r = a.post("/v1/friends/requests", json={"friend_code": "does-not-exist"})
        assert r.status_code == 404

    def test_self_friend_code_returns_400(self, multi_user_e2e):
        a = multi_user_e2e.as_user("user-a")
        own_code = a.get("/v1/users/me").json()["friend_code"]
        r = a.post("/v1/friends/requests", json={"friend_code": own_code})
        assert r.status_code == 400

    def test_accept_then_friend_list_has_display_name(self, multi_user_e2e):
        a = multi_user_e2e.as_user("user-a", name="Alice")
        b = multi_user_e2e.as_user("user-b", name="Bob")

        b_code = b.get("/v1/users/me").json()["friend_code"]
        friendship_id = a.post("/v1/friends/requests", json={"friend_code": b_code}).json()["id"]

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
        r = b.post("/v1/friends/requests", json={"friend_code": a_code})
        assert r.status_code in (400, 403, 409)


class TestEmailFriendRequest:
    """이메일 경로 — 항상 균일 202(존재/자기자신/중복/차단 비노출)"""

    def test_add_by_email_creates_request(self, multi_user_e2e):
        a = multi_user_e2e.as_user("user-a", name="Alice")
        b = multi_user_e2e.as_user("user-b", name="Bob")
        b.get("/v1/users/me")  # B 동기화(verified_email 인덱싱)
        b_email = multi_user_e2e.get_user("user-b").email

        r = a.post("/v1/friends/requests", json={"email": b_email})
        assert r.status_code == 202
        assert r.json() == {"ok": True}

        received = b.get("/v1/friends/requests/received").json()
        assert len(received) == 1
        assert received[0]["requester_display_name"] == "Alice"

    def test_unknown_email_uniform_202_no_request(self, multi_user_e2e):
        a = multi_user_e2e.as_user("user-a")
        r = a.post("/v1/friends/requests", json={"email": "nobody@nowhere.example"})
        assert r.status_code == 202
        assert r.json() == {"ok": True}
        assert a.get("/v1/friends/requests/sent").json() == []

    def test_self_email_uniform_202_no_request(self, multi_user_e2e):
        a = multi_user_e2e.as_user("user-a")
        a_email = multi_user_e2e.get_user("user-a").email
        r = a.post("/v1/friends/requests", json={"email": a_email})
        assert r.status_code == 202  # 자기자신도 균일 202
        assert a.get("/v1/friends/requests/sent").json() == []  # 요청 미생성

    def test_duplicate_email_uniform_202_single_request(self, multi_user_e2e):
        a = multi_user_e2e.as_user("user-a")
        b = multi_user_e2e.as_user("user-b")
        b.get("/v1/users/me")
        b_email = multi_user_e2e.get_user("user-b").email

        first = a.post("/v1/friends/requests", json={"email": b_email})
        second = a.post("/v1/friends/requests", json={"email": b_email})
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

        r = a.post("/v1/friends/requests", json={"email": "user-b@example.com"})
        assert r.status_code == 202
        assert b.get("/v1/friends/requests/received").json() == []


class TestGlobalProfileSync:
    """비소셜(인증) 엔드포인트 호출만으로도 프로필·verified_email이 동기화됨"""

    def test_sync_on_non_social_endpoint_enables_email_add(self, multi_user_e2e):
        a = multi_user_e2e.as_user("user-a", name="Alice")
        b = multi_user_e2e.as_user("user-b", name="Bob")

        # A는 소셜 엔드포인트(/users/me·/friends)를 전혀 안 거치고 schedules만 호출
        resp = a.get(
            "/v1/schedules",
            params={"start_date": "2024-01-01T00:00:00Z", "end_date": "2024-01-01T23:59:59Z"},
        )
        assert resp.status_code == 200

        # 그래도 B가 A를 이메일로 추가 가능(전역 동기화로 A의 verified_email 확보됨)
        a_email = multi_user_e2e.get_user("user-a").email
        r = b.post("/v1/friends/requests", json={"email": a_email})
        assert r.status_code == 202

        received_a = a.get("/v1/friends/requests/received").json()
        assert len(received_a) == 1
        assert received_a[0]["requester_display_name"] == "Bob"


class TestConsent:
    """이용약관·개인정보처리방침·만 14세 이상 동의 (PUT /v1/users/me/consent)"""

    @staticmethod
    def _agree(client, **overrides):
        """클라이언트처럼 GET /users/me가 알려 준 버전으로 동의"""
        body = {
            "version": client.get("/v1/users/me").json()["consent_version"],
            "age_over_14": True,
            "terms": True,
            "privacy": True,
        }
        body.update(overrides)
        return client.put("/v1/users/me/consent", json=body)

    def test_new_user_requires_consent(self, e2e_client):
        assert e2e_client.get("/v1/users/me").json()["consent_required"] is True

    def test_consent_clears_requirement_and_persists(self, e2e_client):
        r = self._agree(e2e_client)
        assert r.status_code == 200, r.json()
        assert r.json()["consent_required"] is False
        assert e2e_client.get("/v1/users/me").json()["consent_required"] is False

    def test_consent_before_profile_exists(self, e2e_client):
        """GET /users/me를 거치지 않은 첫 요청이 동의여도 프로필이 생기고 기록된다"""
        import app.core.config as app_config

        body = {
            "version": app_config.settings.CONSENT_VERSION,
            "age_over_14": True,
            "terms": True,
            "privacy": True,
        }
        r = e2e_client.put("/v1/users/me/consent", json=body)
        assert r.status_code == 200, r.json()
        assert r.json()["friend_code"]
        assert r.json()["consent_required"] is False

    def test_profile_reports_current_version(self, e2e_client, monkeypatch):
        import app.core.config as app_config

        monkeypatch.setattr(app_config.settings, "CONSENT_VERSION", "2099-01-01")
        assert e2e_client.get("/v1/users/me").json()["consent_version"] == "2099-01-01"

    def test_consent_is_idempotent(self, e2e_client):
        assert self._agree(e2e_client).status_code == 200
        r = self._agree(e2e_client)
        assert r.status_code == 200
        assert r.json()["consent_required"] is False

    def test_each_item_must_be_true(self, e2e_client):
        for field in ("age_over_14", "terms", "privacy"):
            r = self._agree(e2e_client, **{field: False})
            assert r.status_code == 422, field
        assert e2e_client.get("/v1/users/me").json()["consent_required"] is True

    def test_missing_item_is_rejected(self, e2e_client):
        version = e2e_client.get("/v1/users/me").json()["consent_version"]
        body = {"version": version, "terms": True, "privacy": True}
        r = e2e_client.put("/v1/users/me/consent", json=body)
        assert r.status_code == 422
        assert e2e_client.get("/v1/users/me").json()["consent_required"] is True

    def test_stale_version_is_rejected(self, e2e_client):
        r = self._agree(e2e_client, version="2000-01-01")
        assert r.status_code == 409
        assert e2e_client.get("/v1/users/me").json()["consent_required"] is True

    def test_new_version_requires_consent_again(self, e2e_client, monkeypatch):
        import app.core.config as app_config

        assert self._agree(e2e_client).status_code == 200
        monkeypatch.setattr(app_config.settings, "CONSENT_VERSION", "2099-01-01")
        assert e2e_client.get("/v1/users/me").json()["consent_required"] is True

        assert self._agree(e2e_client).status_code == 200
        assert e2e_client.get("/v1/users/me").json()["consent_required"] is False

    def test_consent_is_per_user(self, multi_user_e2e):
        a = multi_user_e2e.as_user("user-a")
        b = multi_user_e2e.as_user("user-b")
        assert self._agree(a).status_code == 200
        assert a.get("/v1/users/me").json()["consent_required"] is False
        assert b.get("/v1/users/me").json()["consent_required"] is True
