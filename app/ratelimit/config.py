"""
Rate Limit 규칙 설정

엔드포인트별 레이트 리밋 규칙 정의 및 매칭 로직
"""
import fnmatch
from typing import List, Optional

from pydantic import BaseModel


class RateLimitRule(BaseModel):
    """
    엔드포인트별 레이트 리밋 규칙
    
    Examples:
        # POST /api/v1/todos에만 적용 (생성 제한)
        RateLimitRule(methods=["POST"], path_pattern="/api/v1/todos", ...)
        
        # /api/v1/todos/* 모든 메서드에 적용
        RateLimitRule(path_pattern="/api/v1/todos/*", ...)
    """
    methods: Optional[List[str]] = None  # None = 모든 메서드, ["POST", "PUT"] = 특정 메서드만
    path_pattern: str                     # fnmatch 패턴: "/api/v1/todos/*", "/api/v1/todos"
    window_seconds: int                   # 윈도우 크기 (초)
    max_requests: int                     # 윈도우 내 최대 요청 수
    
    def matches(self, method: str, path: str) -> bool:
        """
        요청이 이 규칙에 매칭되는지 확인
        
        :param method: HTTP 메서드 (GET, POST, etc.)
        :param path: 요청 경로
        :return: 매칭 여부
        """
        # 메서드 체크
        if self.methods is not None:
            if method.upper() not in [m.upper() for m in self.methods]:
                return False
        
        # 경로 패턴 매칭 (fnmatch 사용)
        return fnmatch.fnmatch(path, self.path_pattern)


# ============================================================
# 기본 규칙 정의
# 규칙 매칭 순서: 위에서 아래로, 첫 번째 매칭 사용
# 더 구체적인 규칙을 위에 배치해야 함
# ============================================================

RATE_LIMIT_RULES: List[RateLimitRule] = [
    # --------------------------------------------------------
    # 엔드포인트별 세분화 규칙 (쓰기 작업에 더 엄격한 제한)
    # --------------------------------------------------------
    RateLimitRule(
        methods=["POST"],
        path_pattern="/v1/todos",
        window_seconds=60,
        max_requests=30,
    ),
    RateLimitRule(
        methods=["POST"],
        path_pattern="/v1/schedules",
        window_seconds=60,
        max_requests=30,
    ),
    RateLimitRule(
        methods=["POST"],
        path_pattern="/v1/timers",
        window_seconds=60,
        max_requests=30,
    ),
    RateLimitRule(
        methods=["POST"],
        path_pattern="/v1/tags",
        window_seconds=60,
        max_requests=30,
    ),
    RateLimitRule(
        methods=["POST"],
        path_pattern="/v1/tags/groups",
        window_seconds=60,
        max_requests=30,
    ),
    
    # --------------------------------------------------------
    # 도메인별 기본 규칙 (읽기 포함 모든 메서드)
    # --------------------------------------------------------
    RateLimitRule(
        path_pattern="/v1/todos/*",
        window_seconds=60,
        max_requests=100,
    ),
    RateLimitRule(
        path_pattern="/v1/todos",
        window_seconds=60,
        max_requests=100,
    ),
    RateLimitRule(
        path_pattern="/v1/schedules/*",
        window_seconds=60,
        max_requests=60,
    ),
    RateLimitRule(
        path_pattern="/v1/schedules",
        window_seconds=60,
        max_requests=60,
    ),
    RateLimitRule(
        path_pattern="/v1/timers/*",
        window_seconds=60,
        max_requests=60,
    ),
    RateLimitRule(
        path_pattern="/v1/timers",
        window_seconds=60,
        max_requests=60,
    ),
    RateLimitRule(
        path_pattern="/v1/tags/*",
        window_seconds=60,
        max_requests=60,
    ),
    RateLimitRule(
        path_pattern="/v1/tags",
        window_seconds=60,
        max_requests=60,
    ),
    RateLimitRule(
        path_pattern="/v1/graphql",
        window_seconds=60,
        max_requests=60,
    ),
    
    # --------------------------------------------------------
    # 전역 폴백 규칙
    # --------------------------------------------------------
    RateLimitRule(
        path_pattern="/v1/*",
        window_seconds=60,
        max_requests=60,
    ),
]


def get_rule_for_request(method: str, path: str) -> Optional[RateLimitRule]:
    """
    요청에 맞는 규칙 찾기 (메서드 + 경로 매칭)
    
    매칭 우선순위:
    1. RATE_LIMIT_RULES 리스트 순서대로 순회
    2. 첫 번째 매칭되는 규칙 반환
    3. 매칭되는 규칙이 없으면 None 반환 (레이트 리밋 미적용)
    
    :param method: HTTP 메서드
    :param path: 요청 경로
    :return: 매칭된 규칙 또는 None
    """
    for rule in RATE_LIMIT_RULES:
        if rule.matches(method, path):
            return rule
    return None


def build_rate_limit_key(user_id: str, method: str, rule: RateLimitRule) -> str:
    """
    레이트 리밋 키 생성
    
    키 구조: "ratelimit:{user_id}:{method}:{path_pattern}"
    
    동일한 규칙(path_pattern)에 대해 사용자별로 독립적인 카운트 유지
    
    :param user_id: 사용자 식별자 (OIDC sub 또는 IP)
    :param method: HTTP 메서드
    :param rule: 적용된 규칙
    :return: 레이트 리밋 키
    """
    # 메서드가 규칙에 명시되어 있으면 메서드 포함, 아니면 "ALL"
    method_key = method.upper() if rule.methods else "ALL"
    return f"ratelimit:{user_id}:{method_key}:{rule.path_pattern}"
