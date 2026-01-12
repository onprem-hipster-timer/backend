"""
Rate Limit Config 테스트
"""
import pytest

from app.ratelimit.config import (
    RateLimitRule,
    get_rule_for_request,
    build_rate_limit_key,
)

pytestmark = pytest.mark.ratelimit


class TestRateLimitRule:
    """RateLimitRule 테스트"""
    
    def test_matches_all_methods(self):
        """메서드 제한 없는 규칙 매칭"""
        rule = RateLimitRule(
            path_pattern="/v1/todos/*",
            window_seconds=60,
            max_requests=100,
        )
        
        assert rule.matches("GET", "/v1/todos/123") is True
        assert rule.matches("POST", "/v1/todos/123") is True
        assert rule.matches("DELETE", "/v1/todos/123") is True
        assert rule.matches("GET", "/v1/schedules/123") is False
    
    def test_matches_specific_methods(self):
        """특정 메서드만 매칭"""
        rule = RateLimitRule(
            methods=["POST", "PUT"],
            path_pattern="/v1/todos/*",
            window_seconds=60,
            max_requests=30,
        )
        
        assert rule.matches("POST", "/v1/todos/123") is True
        assert rule.matches("PUT", "/v1/todos/123") is True
        assert rule.matches("GET", "/v1/todos/123") is False
        assert rule.matches("DELETE", "/v1/todos/123") is False
    
    def test_matches_exact_path(self):
        """정확한 경로 매칭"""
        rule = RateLimitRule(
            methods=["POST"],
            path_pattern="/v1/todos",
            window_seconds=60,
            max_requests=30,
        )
        
        assert rule.matches("POST", "/v1/todos") is True
        assert rule.matches("POST", "/v1/todos/123") is False
    
    def test_matches_method_case_insensitive(self):
        """메서드 대소문자 무관"""
        rule = RateLimitRule(
            methods=["post"],
            path_pattern="/v1/*",
            window_seconds=60,
            max_requests=60,
        )
        
        assert rule.matches("POST", "/v1/todos") is True
        assert rule.matches("post", "/v1/todos") is True


class TestGetRuleForRequest:
    """get_rule_for_request 테스트"""
    
    def test_returns_first_matching_rule(self):
        """첫 번째 매칭 규칙 반환"""
        # POST /v1/todos는 더 구체적인 규칙 먼저 매칭
        rule = get_rule_for_request("POST", "/v1/todos")
        
        assert rule is not None
        assert rule.methods == ["POST"]
        assert rule.max_requests == 30
    
    def test_fallback_to_general_rule(self):
        """일반 규칙으로 폴백"""
        # GET /v1/todos는 methods 제한 없는 규칙 매칭
        rule = get_rule_for_request("GET", "/v1/todos")
        
        assert rule is not None
        assert rule.methods is None  # 모든 메서드
    
    def test_no_match_returns_none(self):
        """매칭 없으면 None"""
        rule = get_rule_for_request("GET", "/health")
        
        assert rule is None
    
    def test_graphql_endpoint(self):
        """GraphQL 엔드포인트 매칭"""
        rule = get_rule_for_request("POST", "/v1/graphql")
        
        assert rule is not None
        assert "/v1/graphql" in rule.path_pattern or "*" in rule.path_pattern


class TestBuildRateLimitKey:
    """build_rate_limit_key 테스트"""
    
    def test_key_with_specific_method(self):
        """특정 메서드 규칙의 키"""
        rule = RateLimitRule(
            methods=["POST"],
            path_pattern="/v1/todos",
            window_seconds=60,
            max_requests=30,
        )
        
        key = build_rate_limit_key("user123", "POST", rule)
        
        assert key == "ratelimit:user123:POST:/v1/todos"
    
    def test_key_with_all_methods(self):
        """모든 메서드 규칙의 키"""
        rule = RateLimitRule(
            path_pattern="/v1/todos/*",
            window_seconds=60,
            max_requests=100,
        )
        
        key = build_rate_limit_key("user123", "GET", rule)
        
        assert key == "ratelimit:user123:ALL:/v1/todos/*"
    
    def test_different_users_different_keys(self):
        """다른 사용자는 다른 키"""
        rule = RateLimitRule(
            path_pattern="/v1/*",
            window_seconds=60,
            max_requests=60,
        )
        
        key1 = build_rate_limit_key("user1", "GET", rule)
        key2 = build_rate_limit_key("user2", "GET", rule)
        
        assert key1 != key2
        assert "user1" in key1
        assert "user2" in key2
