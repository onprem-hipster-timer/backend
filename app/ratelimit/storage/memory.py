"""
인메모리 Rate Limit Storage

단일 인스턴스 환경에서 사용하는 dict 기반 저장소
슬라이딩 윈도우 알고리즘 구현
"""
import asyncio
import time
from typing import Dict, List

from app.ratelimit.storage.base import RateLimitResult, RateLimitStorage


class InMemoryStorage(RateLimitStorage):
    """
    인메모리 슬라이딩 윈도우 저장소
    
    특징:
    - dict 기반으로 키별 타임스탬프 리스트 저장
    - asyncio.Lock으로 동시성 제어
    - 주기적 cleanup으로 메모리 관리 필요
    
    제한:
    - 단일 프로세스/인스턴스에서만 유효
    - 서버 재시작 시 데이터 손실
    - 멀티 인스턴스 환경에서는 Redis 사용 권장
    """

    def __init__(self):
        # key -> [timestamp, timestamp, ...] (정렬된 타임스탬프 리스트)
        self._requests: Dict[str, List[float]] = {}
        self._lock = asyncio.Lock()

    async def record_request(
            self,
            key: str,
            window_seconds: int,
            max_requests: int,
    ) -> RateLimitResult:
        """
        요청 기록 및 레이트 리밋 체크
        
        슬라이딩 윈도우:
        1. 현재 시간 기준 window_seconds 이전의 오래된 요청 제거
        2. 새 요청 타임스탬프 추가
        3. 현재 카운트가 max_requests 이하인지 확인
        """
        now = time.time()
        window_start = now - window_seconds

        async with self._lock:
            # 키가 없으면 빈 리스트로 초기화
            if key not in self._requests:
                self._requests[key] = []

            # 윈도우 밖의 오래된 요청 제거
            self._requests[key] = [
                ts for ts in self._requests[key]
                if ts > window_start
            ]

            current_count = len(self._requests[key])

            # 한도 초과 체크 (새 요청 추가 전에 체크)
            if current_count >= max_requests:
                # 가장 오래된 요청이 만료되는 시간 계산
                if self._requests[key]:
                    oldest = min(self._requests[key])
                    reset_after = int(oldest + window_seconds - now) + 1
                else:
                    reset_after = window_seconds

                return RateLimitResult(
                    allowed=False,
                    current_count=current_count,
                    max_requests=max_requests,
                    reset_after=max(1, reset_after),
                )

            # 새 요청 기록
            self._requests[key].append(now)
            current_count += 1

            # 윈도우 리셋 시간 계산
            if self._requests[key]:
                oldest = min(self._requests[key])
                reset_after = int(oldest + window_seconds - now) + 1
            else:
                reset_after = window_seconds

            return RateLimitResult(
                allowed=True,
                current_count=current_count,
                max_requests=max_requests,
                reset_after=max(1, reset_after),
            )

    async def get_current_count(self, key: str, window_seconds: int) -> int:
        """현재 윈도우 내 요청 수 조회"""
        now = time.time()
        window_start = now - window_seconds

        async with self._lock:
            if key not in self._requests:
                return 0

            # 윈도우 내 요청만 카운트
            return len([
                ts for ts in self._requests[key]
                if ts > window_start
            ])

    async def reset(self, key: str) -> None:
        """특정 키 초기화"""
        async with self._lock:
            if key in self._requests:
                del self._requests[key]

    async def cleanup_expired(self) -> int:
        """
        만료된 엔트리 정리
        
        기본 윈도우(5분)보다 오래된 모든 타임스탬프 제거
        빈 키는 삭제
        """
        now = time.time()
        # 5분보다 오래된 것은 어떤 규칙에서도 사용하지 않음
        max_window = 300
        window_start = now - max_window
        cleaned = 0

        async with self._lock:
            keys_to_delete = []

            for key, timestamps in self._requests.items():
                original_len = len(timestamps)
                self._requests[key] = [
                    ts for ts in timestamps
                    if ts > window_start
                ]
                cleaned += original_len - len(self._requests[key])

                # 빈 리스트는 삭제 대상
                if not self._requests[key]:
                    keys_to_delete.append(key)

            for key in keys_to_delete:
                del self._requests[key]
                cleaned += 1

        return cleaned


# 싱글톤 인스턴스 (앱 전역에서 공유)
_storage_instance: InMemoryStorage | None = None


def get_storage() -> InMemoryStorage:
    """
    저장소 싱글톤 인스턴스 반환
    
    향후 Redis 등 다른 저장소로 교체 시 이 함수만 수정
    """
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = InMemoryStorage()
    return _storage_instance


def reset_storage() -> None:
    """
    저장소 인스턴스 초기화 (테스트용)
    """
    global _storage_instance
    _storage_instance = None
