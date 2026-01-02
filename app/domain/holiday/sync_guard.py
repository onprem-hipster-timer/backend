"""
Holiday Sync Guard

동기화 중복 방지 및 범위 완료 추적을 담당하는 클래스

객체지향 원칙 준수:
- Single Responsibility: 동기화 중복 방지만 담당
- Open/Closed: 동기화 로직은 콜백으로 주입받아 확장 가능
- 전역 인스턴스로 애플리케이션 전체에서 공유
"""
import asyncio
import logging
from typing import Callable, Awaitable, Optional

logger = logging.getLogger(__name__)


class HolidaySyncGuard:
    """
    공휴일 동기화 중복 방지 가드

    - 연도별로 동기화 진행 상태를 추적
    - 같은 연도가 이미 진행 중이면 완료를 기다림 (중복 실행 방지)
    - 범위 요청 시 각 연도별로 완료를 기다려 전체 범위가 완료되면 반환

    사용 예시:
        guard = HolidaySyncGuard()
        await guard.sync_year(2024, sync_func)  # 단일 연도
        await guard.sync_year(2024, 2026, sync_func)  # 범위
    """

    def __init__(self):
        """HolidaySyncGuard 초기화"""
        self._lock = asyncio.Lock()
        self._in_flight: dict[int, asyncio.Event] = {}  # year -> completion event

    async def _sync_single_year(
            self,
            year: int,
            sync_func: Callable[[int], Awaitable[None]],
    ) -> None:
        """
        단일 연도 동기화 내부 구현 (중복 방지)

        - 이미 진행 중이면 완료를 기다림
        - 진행 중이 아니면 동기화 직접 실행

        :param year: 동기화할 연도
        :param sync_func: 실제 동기화를 수행하는 비동기 함수
        """
        async with self._lock:
            if year in self._in_flight:
                # 이미 진행 중: 완료 이벤트만 가져옴
                event = self._in_flight[year]
                waiting = True
                logger.debug(f"Year {year} sync already in progress, waiting...")
            else:
                # 새로 시작: 이벤트 생성
                event = asyncio.Event()
                self._in_flight[year] = event
                waiting = False
                logger.debug(f"Year {year} sync started")

        if waiting:
            # 이미 진행 중인 경우: 완료 대기만
            await event.wait()
        else:
            # 새로 시작: 직접 실행
            try:
                await sync_func(year)
                logger.info(f"Year {year} sync completed successfully")
            except Exception as e:
                logger.error(f"Year {year} sync failed: {str(e)}", exc_info=True)
                raise  # 예외를 호출자에게 전파
            finally:
                async with self._lock:
                    self._in_flight.pop(year, None)
                event.set()

    async def sync_year(
            self,
            year: int,
            sync_func: Callable[[int], Awaitable[None]],
            end_year: Optional[int] = None,
    ) -> None:
        """
        공휴일 동기화 (중복 방지)

        - 단일 연도: end_year가 None인 경우
        - 범위 동기화: end_year가 지정된 경우 (각 연도별 중복 방지 + 전체 완료 추적)

        :param year: 동기화할 연도 (또는 시작 연도)
        :param sync_func: 실제 동기화를 수행하는 비동기 함수
        :param end_year: 종료 연도 (포함). None이면 year만 동기화
        """
        if end_year is None:
            # 단일 연도 동기화
            await self._sync_single_year(year, sync_func)
        else:
            # 범위 동기화: 각 연도별로 병렬 실행
            tasks = [
                self._sync_single_year(y, sync_func)
                for y in range(year, end_year + 1)
            ]
            await asyncio.gather(*tasks)
            logger.info(f"All years {year}-{end_year} sync completed")

    def is_syncing(self, year: int) -> bool:
        """
        특정 연도가 현재 동기화 중인지 확인

        :param year: 확인할 연도
        :return: 동기화 중이면 True
        """
        return year in self._in_flight


# 전역 인스턴스 (애플리케이션 전체에서 공유)
_sync_guard: HolidaySyncGuard | None = None


def get_sync_guard() -> HolidaySyncGuard:
    """
    전역 SyncGuard 인스턴스 반환

    싱글톤 패턴으로 애플리케이션 전체에서 동일한 인스턴스 사용

    :return: HolidaySyncGuard 인스턴스
    """
    global _sync_guard
    if _sync_guard is None:
        _sync_guard = HolidaySyncGuard()
    return _sync_guard
