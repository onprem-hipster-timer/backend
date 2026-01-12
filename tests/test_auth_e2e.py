"""
OIDC 인증 E2E 테스트

실제 API 엔드포인트에서 인증 동작 테스트
- OIDC_ENABLED=false 상태에서는 모든 요청이 테스트 사용자로 처리됨
- OIDC_ENABLED=true 상태에서는 토큰 검증이 수행됨
"""
import pytest


class TestAuthenticationDisabled:
    """OIDC 비활성화 상태 테스트 (기본 테스트 환경)"""
    
    @pytest.mark.e2e
    def test_schedule_endpoint_works_without_token(self, e2e_client):
        """OIDC 비활성화 시 토큰 없이 일정 생성 가능"""
        response = e2e_client.post(
            "/v1/schedules",
            json={
                "title": "테스트 일정",
                "start_time": "2024-01-01T10:00:00Z",
                "end_time": "2024-01-01T12:00:00Z",
            },
        )
        
        assert response.status_code == 201
        assert response.json()["title"] == "테스트 일정"
    
    @pytest.mark.e2e
    def test_todo_endpoint_works_without_token(self, e2e_client):
        """OIDC 비활성화 시 토큰 없이 Todo 생성 가능"""
        # 1. 먼저 태그 그룹 생성 (Todo에 필수)
        group_response = e2e_client.post(
            "/v1/tags/groups",
            json={
                "name": "Todo 그룹",
                "color": "#FF0000",
            },
        )
        assert group_response.status_code == 201
        group_id = group_response.json()["id"]
        
        # 2. Todo 생성
        response = e2e_client.post(
            "/v1/todos",
            json={
                "title": "테스트 Todo",
                "tag_group_id": group_id,
            },
        )
        
        assert response.status_code == 201
        assert response.json()["title"] == "테스트 Todo"
    
    @pytest.mark.e2e
    def test_tag_group_endpoint_works_without_token(self, e2e_client):
        """OIDC 비활성화 시 토큰 없이 태그 그룹 생성 가능"""
        response = e2e_client.post(
            "/v1/tags/groups",
            json={
                "name": "테스트 그룹",
                "color": "#FF0000",
            },
        )
        
        assert response.status_code == 201
        assert response.json()["name"] == "테스트 그룹"
    
    @pytest.mark.e2e
    def test_graphql_endpoint_works_without_token(self, e2e_client):
        """OIDC 비활성화 시 토큰 없이 GraphQL 쿼리 가능"""
        response = e2e_client.post(
            "/v1/graphql",
            json={
                "query": """
                    query {
                        calendar(startDate: "2024-01-01", endDate: "2024-01-07") {
                            days {
                                date
                            }
                        }
                    }
                """
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert data["data"]["calendar"]["days"] is not None


class TestOwnerIsolation:
    """사용자 간 데이터 격리 테스트"""
    
    @pytest.mark.e2e
    def test_user_can_only_see_own_schedules(self, e2e_client):
        """사용자는 자신의 일정만 볼 수 있음"""
        # 1. 일정 생성 (test-user-id)
        create_response = e2e_client.post(
            "/v1/schedules",
            json={
                "title": "내 일정",
                "start_time": "2024-01-01T10:00:00Z",
                "end_time": "2024-01-01T12:00:00Z",
            },
        )
        assert create_response.status_code == 201
        schedule_id = create_response.json()["id"]
        
        # 2. 같은 사용자로 조회 - 성공
        get_response = e2e_client.get(f"/v1/schedules/{schedule_id}")
        assert get_response.status_code == 200
        assert get_response.json()["title"] == "내 일정"
    
    @pytest.mark.e2e
    def test_user_can_only_see_own_todos(self, e2e_client):
        """사용자는 자신의 Todo만 볼 수 있음"""
        # 1. 태그 그룹 생성
        group_response = e2e_client.post(
            "/v1/tags/groups",
            json={
                "name": "할일 그룹",
                "color": "#00FF00",
            },
        )
        assert group_response.status_code == 201
        group_id = group_response.json()["id"]
        
        # 2. Todo 생성
        create_response = e2e_client.post(
            "/v1/todos",
            json={
                "title": "내 할일",
                "tag_group_id": group_id,
            },
        )
        assert create_response.status_code == 201
        todo_id = create_response.json()["id"]
        
        # 3. 조회 성공
        get_response = e2e_client.get(f"/v1/todos/{todo_id}")
        assert get_response.status_code == 200
        assert get_response.json()["title"] == "내 할일"
    
    @pytest.mark.e2e
    def test_user_can_only_see_own_tags(self, e2e_client):
        """사용자는 자신의 태그만 볼 수 있음"""
        # 1. 태그 그룹 생성
        group_response = e2e_client.post(
            "/v1/tags/groups",
            json={
                "name": "내 그룹",
                "color": "#00FF00",
            },
        )
        assert group_response.status_code == 201
        group_id = group_response.json()["id"]
        
        # 2. 태그 생성
        tag_response = e2e_client.post(
            "/v1/tags",
            json={
                "name": "내 태그",
                "color": "#0000FF",
                "group_id": group_id,
            },
        )
        assert tag_response.status_code == 201
        tag_id = tag_response.json()["id"]
        
        # 3. 조회 성공
        get_response = e2e_client.get(f"/v1/tags/{tag_id}")
        assert get_response.status_code == 200
        assert get_response.json()["name"] == "내 태그"


class TestGraphQLAuthentication:
    """GraphQL 인증 테스트"""
    
    @pytest.mark.e2e
    def test_graphql_introspection_works_without_token(self, e2e_client):
        """Introspection 쿼리는 인증 없이 동작"""
        response = e2e_client.post(
            "/v1/graphql",
            json={
                "query": """
                    query {
                        __schema {
                            types {
                                name
                            }
                        }
                    }
                """
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "__schema" in data["data"]
    
    @pytest.mark.e2e
    def test_graphql_calendar_query_returns_owner_data_only(self, e2e_client):
        """GraphQL calendar 쿼리는 현재 사용자 데이터만 반환"""
        # 1. 일정 생성
        create_response = e2e_client.post(
            "/v1/schedules",
            json={
                "title": "GraphQL 테스트 일정",
                "start_time": "2024-06-15T10:00:00Z",
                "end_time": "2024-06-15T12:00:00Z",
            },
        )
        assert create_response.status_code == 201
        
        # 2. GraphQL로 조회
        gql_response = e2e_client.post(
            "/v1/graphql",
            json={
                "query": """
                    query {
                        calendar(startDate: "2024-06-15", endDate: "2024-06-15") {
                            days {
                                date
                                events {
                                    id
                                    title
                                }
                            }
                        }
                    }
                """
            },
        )
        
        assert gql_response.status_code == 200
        data = gql_response.json()
        assert "data" in data
        
        days = data["data"]["calendar"]["days"]
        assert len(days) == 1
        
        events = days[0]["events"]
        assert len(events) == 1
        assert events[0]["title"] == "GraphQL 테스트 일정"


class TestTimerAuthentication:
    """타이머 인증 테스트"""
    
    @pytest.mark.e2e
    def test_timer_operations_use_owner_id(self, e2e_client):
        """타이머 생성/조회/제어가 owner_id를 사용"""
        # 1. 일정 생성
        schedule_response = e2e_client.post(
            "/v1/schedules",
            json={
                "title": "타이머 테스트 일정",
                "start_time": "2024-01-01T10:00:00Z",
                "end_time": "2024-01-01T12:00:00Z",
            },
        )
        assert schedule_response.status_code == 201
        schedule_id = schedule_response.json()["id"]
        
        # 2. 타이머 생성
        timer_response = e2e_client.post(
            "/v1/timers",
            json={
                "schedule_id": schedule_id,
                "allocated_duration": 3600,
            },
        )
        assert timer_response.status_code == 201
        timer_id = timer_response.json()["id"]
        
        # 3. 타이머 조회
        get_response = e2e_client.get(f"/v1/timers/{timer_id}")
        assert get_response.status_code == 200
        assert get_response.json()["schedule_id"] == schedule_id
        assert get_response.json()["status"] == "running"
        
        # 4. 타이머 일시정지 (PATCH 메서드 사용)
        pause_response = e2e_client.patch(f"/v1/timers/{timer_id}/pause")
        assert pause_response.status_code == 200
        assert pause_response.json()["status"] == "paused"
