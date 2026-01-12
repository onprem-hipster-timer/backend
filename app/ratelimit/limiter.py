"""
Rate Limiter 핵심 로직

슬라이딩 윈도우 기반 레이트 리밋 서비스
"""
from app.ratelimit.config import RateLimitRule, build_rate_limit_key
from app.ratelimit.storage.base import RateLimitResult
from app.ratelimit.storage.memory import get_storage


class RateLimiter:
    """
    레이트 리밋 서비스
    
    저장소를 사용하여 슬라이딩 윈도우 레이트 리밋 수행
    """
    
    def __init__(self):
        self._storage = get_storage()
    
    async def check_and_record(
        self,
        user_id: str,
        method: str,
        rule: RateLimitRule,
    ) -> RateLimitResult:
        """
        요청을 체크하고 기록
        
        :param user_id: 사용자 식별자
        :param method: HTTP 메서드
        :param rule: 적용할 규칙
        :return: 레이트 리밋 결과
        """
        key = build_rate_limit_key(user_id, method, rule)
        return await self._storage.record_request(
            key=key,
            window_seconds=rule.window_seconds,
            max_requests=rule.max_requests,
        )
    
    async def get_remaining(
        self,
        user_id: str,
        method: str,
        rule: RateLimitRule,
    ) -> int:
        """
        남은 요청 수 조회 (기록하지 않음)
        
        :param user_id: 사용자 식별자
        :param method: HTTP 메서드
        :param rule: 적용할 규칙
        :return: 남은 요청 수
        """
        key = build_rate_limit_key(user_id, method, rule)
        current = await self._storage.get_current_count(key, rule.window_seconds)
        return max(0, rule.max_requests - current)
    
    async def reset_user(self, user_id: str, method: str, rule: RateLimitRule) -> None:
        """
        특정 사용자의 레이트 리밋 초기화
        
        :param user_id: 사용자 식별자
        :param method: HTTP 메서드
        :param rule: 적용할 규칙
        """
        key = build_rate_limit_key(user_id, method, rule)
        await self._storage.reset(key)
    
    async def cleanup(self) -> int:
        """
        만료된 엔트리 정리
        
        :return: 정리된 엔트리 수
        """
        return await self._storage.cleanup_expired()


# 싱글톤 인스턴스
_limiter_instance: RateLimiter | None = None


def get_limiter() -> RateLimiter:
    """레이트 리미터 싱글톤 인스턴스 반환"""
    global _limiter_instance
    if _limiter_instance is None:
        _limiter_instance = RateLimiter()
    return _limiter_instance


def reset_limiter() -> None:
    """레이트 리미터 인스턴스 초기화 (테스트용)"""
    global _limiter_instance
    _limiter_instance = None
