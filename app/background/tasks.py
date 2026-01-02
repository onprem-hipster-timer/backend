"""
백그라운드 태스크

공휴일 주기 동기화 태스크
lifespan 내부에서 실행될 async 태스크

객체지향 원칙 준수:
- Single Responsibility: 각 메서드는 하나의 책임만 담당
- 메서드 분리로 재사용성 및 테스트 용이성 향상
- 메서드 체이닝으로 가독성 향상
- SyncGuard를 통해 동기화 중복 방지
"""
import asyncio
import logging
from datetime import datetime

from app.db.session import get_async_db
from app.domain.holiday.service import HolidayService
from app.domain.holiday.sync_guard import get_sync_guard

logger = logging.getLogger(__name__)


class HolidayBackgroundTask:
    """
    공휴일 주기 동기화 태스크
    
    객체지향 원칙 준수:
    - 각 단계를 별도 메서드로 분리
    - 메서드 체이닝으로 가독성 향상
    """

    # 설정
    INTERVAL_SECONDS = 3600 * 24  # 24시간
    INITIAL_YEAR = 2010  # 초기 동기화 시작 연도

    def __init__(self):
        """HolidayBackgroundTask 초기화"""
        self.is_running = False
        self.is_initialized = False  # 초기화 완료 플래그

    async def _sync_years(self, years: list[int]) -> None:
        """
        여러 연도 동기화
        
        :param years: 동기화할 연도 목록
        """
        for year in years:
            await self._sync_holidays(year)

    async def _handle_initialization(self, current_year: int) -> None:
        """
        초기화 처리
        
        :param current_year: 현재 연도
        """
        if not self.is_initialized:
            await self._initialize_historical_data(current_year)
            self.is_initialized = True

    async def _handle_regular_sync(self, current_year: int) -> None:
        """
        정기 동기화 처리
        
        :param current_year: 현재 연도
        """
        await self._sync_years([current_year, current_year + 1])
        logger.info(f"Holiday sync completed at {datetime.now().isoformat()}")

    async def run(self) -> None:
        """
        공휴일 주기 동기화 (lifespan startup 후 실행)
        
        객체지향 원칙 준수:
        - 각 단계를 별도 메서드로 분리
        - 메서드 체이닝으로 가독성 향상
        
        첫 실행 시:
        1. 2010년부터 현재 연도까지 모든 연도 동기화 (초기 데이터 로드)
        
        이후 실행:
        1. 현재 연도 + 내년 공휴일 조회
        2. 저장된 해시와 비교
        3. 변경 있으면 DB 업데이트
        4. INTERVAL_SECONDS 만큼 대기
        5. asyncio.CancelledError 시 정상 종료
        6. 모든 예외 발생 시 배치 작업 중단
        """
        self.is_running = True
        logger.info("Holiday background task started")

        try:
            while self.is_running:
                current_year = datetime.now().year
                await self._handle_initialization(current_year)
                await self._handle_regular_sync(current_year)
                await asyncio.sleep(self.INTERVAL_SECONDS)

        except asyncio.CancelledError:
            logger.info("Holiday background task cancelled (shutdown)")
            self.is_running = False
        except Exception as e:
            # 모든 예외 발생 시 배치 작업 중단
            logger.error(
                f"Error during holiday sync, stopping batch task: {str(e)}",
                exc_info=True
            )
            self.is_running = False

    async def _initialize_historical_data(self, current_year: int) -> None:
        """
        초기 데이터 로드: 2010년부터 현재 연도까지 모든 연도 동기화
        
        서버 처음 실행 시:
        - 해시 테이블에 이미 존재하는 년도는 해시 비교 없이 건너뜀
        - 존재하지 않는 년도만 동기화
        
        객체지향 원칙 준수:
        - 각 단계를 별도 메서드로 분리
        
        예외 발생 시 즉시 중단
        
        :param current_year: 현재 연도
        :raises Exception: 모든 예외를 그대로 전파하여 배치 작업 중단
        """
        # 해시 테이블에 존재하는 년도 조회
        async with get_async_db() as session:
            service = HolidayService(session)
            existing_years = await service.get_existing_years()

        years_to_sync = list(range(self.INITIAL_YEAR, current_year + 1))

        # 해시 테이블에 존재하지 않는 년도만 필터링
        years_to_initialize = [year for year in years_to_sync if year not in existing_years]
        skipped_count = len(years_to_sync) - len(years_to_initialize)

        if skipped_count > 0:
            logger.info(
                f"Skipping {skipped_count} years that already exist in hash table: "
                f"{sorted(existing_years)}"
            )

        if not years_to_initialize:
            logger.info(
                f"All years from {self.INITIAL_YEAR} to {current_year} already exist in hash table. "
                f"Skipping initialization."
            )
            return

        total_years = len(years_to_initialize)
        logger.info(
            f"Initializing historical holiday data from {self.INITIAL_YEAR} to {current_year} "
            f"({total_years} years to sync, {skipped_count} years skipped)"
        )

        for idx, year in enumerate(years_to_initialize, 1):
            await self._sync_holidays(year, force_update=True)
            logger.info(f"   [{idx}/{total_years}] {year} year initialized")

        logger.info(
            f"Historical data initialization completed: "
            f"all {total_years} years succeeded"
        )

    async def _sync_holidays(self, year: int, force_update: bool = False) -> None:
        """
        특정 연도 공휴일 동기화 로직 (SyncGuard를 통해 중복 방지)
        
        객체지향 원칙 준수:
        - 각 단계를 별도 메서드로 분리
        - Service를 통해 모든 비즈니스 로직 처리
        - SyncGuard를 통해 동기화 중복 방지
        
        해시가 중복되면 해당 연도는 수정을 시도하지 않음
        
        :param year: 동기화할 연도
        :param force_update: True인 경우 해시 비교 없이 무조건 업데이트 (초기화 시 사용)
        :raises Exception: 모든 예외를 그대로 전파
        """
        guard = get_sync_guard()

        async def do_sync(y: int) -> None:
            """실제 동기화 수행 (SyncGuard 콜백)"""
            async with get_async_db() as session:
                service = HolidayService(session)
                await service.sync_holidays_for_year(y, force_update)

        await guard.sync_year(year, do_sync)


async def sync_holidays_async(start_year: int, end_year: int) -> None:
    """
    공휴일 동기화를 비동기로 수행 (배치/백그라운드용)

    SyncGuard를 사용하여 중복 실행 방지 및 범위 완료 추적
    """
    guard = get_sync_guard()

    async def sync_single_year(year: int) -> None:
        """단일 연도 동기화 (SyncGuard 콜백용)"""
        async with get_async_db() as session:
            service = HolidayService(session)
            await service.sync_holidays_for_year(year, force_update=True)

    await guard.sync_years(start_year, end_year, sync_single_year)
