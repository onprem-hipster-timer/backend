"""
Friend API E2E 테스트

친구 관계 API 엔드포인트 테스트
"""
import pytest


class TestFriendRequestAPI:
    """친구 요청 API 테스트"""

    def test_send_friend_request_success(self, e2e_client):
        """친구 요청 전송 성공"""
        response = e2e_client.post(
            "/v1/friends/requests",
            json={"addressee_id": "target-user-id"},
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["requester_id"] == "test-user-id"
        assert data["addressee_id"] == "target-user-id"
        assert data["status"] == "pending"

    def test_send_friend_request_to_self_fails(self, e2e_client):
        """자기 자신에게 친구 요청 실패"""
        response = e2e_client.post(
            "/v1/friends/requests",
            json={"addressee_id": "test-user-id"},
        )
        
        assert response.status_code == 400

    def test_duplicate_friend_request_fails(self, e2e_client):
        """중복 친구 요청 실패"""
        # 첫 번째 요청
        e2e_client.post(
            "/v1/friends/requests",
            json={"addressee_id": "another-user-id"},
        )
        
        # 두 번째 요청
        response = e2e_client.post(
            "/v1/friends/requests",
            json={"addressee_id": "another-user-id"},
        )
        
        assert response.status_code == 409


class TestFriendListAPI:
    """친구 목록 API 테스트"""

    def test_list_friends_empty(self, e2e_client):
        """친구 목록 조회 - 빈 목록"""
        response = e2e_client.get("/v1/friends")
        
        assert response.status_code == 200
        assert response.json() == []

    def test_list_friend_ids(self, e2e_client):
        """친구 ID 목록 조회"""
        response = e2e_client.get("/v1/friends/ids")
        
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_check_friendship_false(self, e2e_client):
        """친구 여부 확인 - False"""
        response = e2e_client.get("/v1/friends/check/unknown-user")
        
        assert response.status_code == 200
        assert response.json() is False


class TestPendingRequestsAPI:
    """대기 중인 친구 요청 API 테스트"""

    def test_list_received_requests(self, e2e_client):
        """받은 친구 요청 목록 조회"""
        response = e2e_client.get("/v1/friends/requests/received")
        
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_list_sent_requests(self, e2e_client):
        """보낸 친구 요청 목록 조회"""
        response = e2e_client.get("/v1/friends/requests/sent")
        
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_list_sent_requests_after_sending(self, e2e_client):
        """친구 요청 후 보낸 요청 목록에 표시"""
        # 친구 요청 전송
        send_response = e2e_client.post(
            "/v1/friends/requests",
            json={"addressee_id": "some-user-id"},
        )
        assert send_response.status_code == 201
        
        # 보낸 요청 목록 조회
        response = e2e_client.get("/v1/friends/requests/sent")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert any(r["addressee_id"] == "some-user-id" for r in data)


class TestBlockAPI:
    """차단 API 테스트"""

    def test_block_user_success(self, e2e_client):
        """사용자 차단 성공"""
        response = e2e_client.post("/v1/friends/block/blocked-user-id")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "blocked"
        assert data["blocked_by"] == "test-user-id"

    def test_unblock_user_success(self, e2e_client):
        """차단 해제 성공"""
        # 먼저 차단
        e2e_client.post("/v1/friends/block/unblock-target-id")
        
        # 차단 해제
        response = e2e_client.delete("/v1/friends/block/unblock-target-id")
        
        assert response.status_code == 200
        assert response.json()["ok"] is True

    def test_block_self_fails(self, e2e_client):
        """자기 자신 차단 실패"""
        response = e2e_client.post("/v1/friends/block/test-user-id")
        
        assert response.status_code == 400


class TestReverseFriendRequest:
    """역방향 친구 요청 테스트 (multi-user)"""

    def test_reverse_friend_request_returns_409(self, multi_user_e2e):
        """
        역방향 친구 요청 시 409 반환
        
        시나리오:
        - userA → userB 요청(PENDING)
        - userB → userA 요청 시도
        - 기대: 409 + 추가 레코드 생성 없음
        """
        client_a = multi_user_e2e.as_user("user-a")
        client_b = multi_user_e2e.as_user("user-b")
        
        user_a_id = multi_user_e2e.get_user("user-a").sub
        user_b_id = multi_user_e2e.get_user("user-b").sub
        
        # 1. userA → userB 친구 요청
        request_a_to_b = client_a.post(
            "/v1/friends/requests",
            json={"addressee_id": user_b_id},
        )
        assert request_a_to_b.status_code == 201, f"Failed: {request_a_to_b.json()}"
        
        # 2. userB → userA 역방향 친구 요청 시도
        request_b_to_a = client_b.post(
            "/v1/friends/requests",
            json={"addressee_id": user_a_id},
        )
        
        # 3. 409 Conflict 반환 확인
        assert request_b_to_a.status_code == 409
        
        # 4. 추가 레코드 생성되지 않았는지 확인
        # userB의 보낸 요청 목록에 userA가 없어야 함
        sent_response = client_b.get("/v1/friends/requests/sent")
        assert sent_response.status_code == 200
        sent_requests = sent_response.json()
        assert not any(r["addressee_id"] == user_a_id for r in sent_requests)

    def test_reverse_friend_request_does_not_create_duplicate(self, multi_user_e2e):
        """
        역방향 친구 요청이 중복 레코드를 생성하지 않음 확인
        
        이미 PENDING인 상태에서 반대 방향 요청 시,
        데이터베이스에 2개의 레코드가 생기면 안 됨
        """
        client_a = multi_user_e2e.as_user("user-a")
        client_b = multi_user_e2e.as_user("user-b")
        
        user_a_id = multi_user_e2e.get_user("user-a").sub
        user_b_id = multi_user_e2e.get_user("user-b").sub
        
        # 1. userA → userB 친구 요청
        client_a.post(
            "/v1/friends/requests",
            json={"addressee_id": user_b_id},
        )
        
        # 2. userB → userA 역방향 친구 요청 시도 (실패 예상)
        client_b.post(
            "/v1/friends/requests",
            json={"addressee_id": user_a_id},
        )
        
        # 3. userA의 받은 요청 목록에 하나만 있어야 함
        # (역방향 요청이 생성되지 않았으므로)
        received_a = client_a.get("/v1/friends/requests/received")
        received_requests = received_a.json()
        user_b_requests = [r for r in received_requests if r["requester_id"] == user_b_id]
        assert len(user_b_requests) == 0, "역방향 요청이 생성되면 안 됨"
        
        # 4. userB의 받은 요청 목록에 userA의 원래 요청은 있어야 함
        received_b = client_b.get("/v1/friends/requests/received")
        received_b_requests = received_b.json()
        user_a_requests = [r for r in received_b_requests if r["requester_id"] == user_a_id]
        assert len(user_a_requests) == 1, "원래 요청은 유지되어야 함"