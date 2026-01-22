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
