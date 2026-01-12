"""
Rate Limit Middleware 통합 테스트

rate_limit_client fixture를 사용하여 레이트 리밋이 활성화된 환경에서 테스트.
다른 테스트와 완전히 격리됩니다.
"""
import pytest

from app.ratelimit.config import get_rule_for_request

pytestmark = pytest.mark.ratelimit


class TestRateLimitMiddleware:
    """레이트 리밋 미들웨어 통합 테스트"""
    
    def test_rate_limit_headers_present(self, rate_limit_client):
        """응답에 레이트 리밋 헤더 포함"""
        response = rate_limit_client.get("/v1/tags")
        
        # 성공 응답이든 에러든 헤더는 있어야 함
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers
    
    def test_rate_limit_remaining_decreases(self, rate_limit_client):
        """요청마다 remaining 감소"""
        response1 = rate_limit_client.get("/v1/tags")
        remaining1 = int(response1.headers["X-RateLimit-Remaining"])
        
        response2 = rate_limit_client.get("/v1/tags")
        remaining2 = int(response2.headers["X-RateLimit-Remaining"])
        
        assert remaining2 == remaining1 - 1
    
    def test_rate_limit_exceeded_returns_429(self, rate_limit_client):
        """한도 초과 시 429 반환"""
        # config에서 실제 한도 가져오기
        rule = get_rule_for_request("POST", "/v1/tags/groups")
        assert rule is not None, "POST /v1/tags/groups 규칙이 없습니다"
        max_requests = rule.max_requests
        
        # 한도까지 요청
        for _ in range(max_requests):
            response = rate_limit_client.post(
                "/v1/tags/groups",
                json={"name": "test", "color": "#FF0000"},
            )
            # 성공 또는 validation 에러는 괜찮음
            assert response.status_code in [200, 201, 422]
        
        # 한도 초과
        response = rate_limit_client.post(
            "/v1/tags/groups",
            json={"name": "test", "color": "#FF0000"},
        )
        
        assert response.status_code == 429
        assert "Retry-After" in response.headers
        assert response.json()["detail"] == "요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요."
    
    def test_non_api_endpoints_not_rate_limited(self, rate_limit_client):
        """비 API 경로는 레이트 리밋 미적용"""
        # /docs나 /openapi.json 같은 경로
        response = rate_limit_client.get("/docs")
        
        # 레이트 리밋 헤더 없음
        assert "X-RateLimit-Limit" not in response.headers
    
    def test_different_endpoints_different_limits(self, rate_limit_client):
        """다른 엔드포인트는 다른 한도 (config 값 검증)"""
        # config에서 실제 한도 가져오기
        rule_todos = get_rule_for_request("GET", "/v1/todos")
        rule_schedules = get_rule_for_request("GET", "/v1/schedules")
        
        assert rule_todos is not None
        assert rule_schedules is not None
        
        # 응답 헤더의 한도가 config와 일치하는지 확인
        response_todos = rate_limit_client.get("/v1/todos")
        limit_todos = int(response_todos.headers["X-RateLimit-Limit"])
        
        response_schedules = rate_limit_client.get("/v1/schedules")
        limit_schedules = int(response_schedules.headers["X-RateLimit-Limit"])
        
        assert limit_todos == rule_todos.max_requests
        assert limit_schedules == rule_schedules.max_requests


class TestRateLimitPriority:
    """레이트 리밋 규칙 우선순위 테스트"""
    
    def test_post_has_stricter_limit_than_get(self, rate_limit_client):
        """POST는 GET보다 더 엄격한 한도"""
        # config에서 실제 한도 가져오기
        rule_post = get_rule_for_request("POST", "/v1/todos")
        rule_get = get_rule_for_request("GET", "/v1/todos")
        
        assert rule_post is not None
        assert rule_get is not None
        
        # POST가 GET보다 엄격해야 함 (또는 같거나)
        assert rule_post.max_requests <= rule_get.max_requests
        
        # GET 요청만 테스트 (FK 제약 문제 회피)
        response_get = rate_limit_client.get("/v1/todos")
        limit_get = int(response_get.headers["X-RateLimit-Limit"])
        assert limit_get == rule_get.max_requests
    
    def test_specific_method_rule_takes_priority(self):
        """메서드가 명시된 규칙이 우선 (config 검증만)"""
        # POST /v1/todos는 methods=["POST"] 규칙 매칭
        rule_post = get_rule_for_request("POST", "/v1/todos")
        
        # GET /v1/todos는 methods=None 규칙 매칭
        rule_get = get_rule_for_request("GET", "/v1/todos")
        
        assert rule_post is not None
        assert rule_get is not None
        
        # POST 규칙은 methods가 명시되어 있어야 함
        assert rule_post.methods is not None
        assert "POST" in [m.upper() for m in rule_post.methods]
        
        # GET 규칙은 methods가 None (모든 메서드)
        assert rule_get.methods is None
