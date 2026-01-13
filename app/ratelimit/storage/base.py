"""
Rate Limit Storage 추상 클래스

Strategy 패턴으로 인메모리/Redis 등 다양한 저장소 구현 지원
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class RateLimitResult:
    """레이트 리밋 체크 결과"""
    allowed: bool  # 요청 허용 여부
    current_count: int  # 현재 윈도우 내 요청 수
    max_requests: int  # 최대 허용 요청 수
    reset_after: int  # 윈도우 리셋까지 남은 초

    @property
    def remaining(self) -> int:
        """남은 요청 수"""
        return max(0, self.max_requests - self.current_count)


class RateLimitStorage(ABC):
    """
    레이트 리밋 저장소 추상 클래스
    
    슬라이딩 윈도우 알고리즘을 위한 저장소 인터페이스
    구현체: InMemoryStorage, (향후) RedisStorage
    """

    @abstractmethod
    async def record_request(
            self,
            key: str,
            window_seconds: int,
            max_requests: int,
    ) -> RateLimitResult:
        """
        요청을 기록하고 레이트 리밋 결과 반환
        
        슬라이딩 윈도우 방식:
        - 현재 시간 기준 window_seconds 이전의 요청만 카운트
        - 새 요청을 기록하고 허용 여부 판단
        
        :param key: 레이트 리밋 키 (예: "user:{sub}:POST:/api/v1/todos")
        :param window_seconds: 윈도우 크기 (초)
        :param max_requests: 윈도우 내 최대 허용 요청 수
        :return: RateLimitResult
        """
        pass

    @abstractmethod
    async def get_current_count(self, key: str, window_seconds: int) -> int:
        """
        현재 윈도우 내 요청 수 조회 (기록하지 않음)
        
        :param key: 레이트 리밋 키
        :param window_seconds: 윈도우 크기 (초)
        :return: 현재 요청 수
        """
        pass

    @abstractmethod
    async def reset(self, key: str) -> None:
        """
        특정 키의 레이트 리밋 초기화
        
        :param key: 레이트 리밋 키
        """
        pass

    @abstractmethod
    async def cleanup_expired(self) -> int:
        """
        만료된 엔트리 정리 (메모리 관리용)
        
        :return: 정리된 엔트리 수
        """
        pass
