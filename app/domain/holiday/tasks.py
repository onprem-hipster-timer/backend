"""
Holiday 백그라운드 태스크

공휴일 주기 동기화 태스크
lifespan 내부에서 실행될 async 태스크

책임:
- 스케줄링 (주기적 실행)
- 상태 관리 (is_running, is_initialized)
- Service 호출 (비즈니스 로직은 Service에 위임)
"""
import asyncio
import logging
from datetime import datetime

from app.db.session import get_async_db
from app.domain.holiday.service import HolidayService

logger = logging.getLogger(__name__)


class HolidayBackgroundTask:
    """
    공휴일 주기 동기화 태스크
    
    스케줄링만 담당하고, 비즈니스 로직은 Service에 위임
    """

    # 설정
    INTERVAL_SECONDS = 3600 * 24  # 24시간
    INITIAL_YEAR = 2010  # 초기 동기화 시작 연도

    def __init__(self):
        """HolidayBackgroundTask 초기화"""
        self.is_running = False
        self.is_initialized = False

    async def run(self) -> None:
        """
        공휴일 주기 동기화 (lifespan startup 후 실행)
        
        첫 실행 시:
        1. 2010년부터 현재 연도까지 모든 연도 동기화 (초기 데이터 로드)
        
        이후 실행:
        1. 현재 연도 + 내년 공휴일 동기화
        2. INTERVAL_SECONDS 만큼 대기
        3. asyncio.CancelledError 시 정상 종료
        """
        self.is_running = True
        logger.info("Holiday background task started")

        try:
            while self.is_running:
                async with get_async_db() as session:
                    service = HolidayService(session)
                    
                    # 초기화 (최초 1회)
                    if not self.is_initialized:
                        current_year = datetime.now().year
                        await service.initialize_historical_data(
                            self.INITIAL_YEAR, current_year
                        )
                        self.is_initialized = True
                    
                    # 정기 동기화
                    await service.sync_current_and_next_year()
                
                await asyncio.sleep(self.INTERVAL_SECONDS)

        except asyncio.CancelledError:
            logger.info("Holiday background task cancelled (shutdown)")
            self.is_running = False
        except Exception as e:
            logger.error(
                f"Error during holiday sync, stopping batch task: {str(e)}",
                exc_info=True
            )
            self.is_running = False


async def sync_holidays_async(start_year: int, end_year: int) -> None:
    """
    공휴일 동기화를 비동기로 수행 (API 트리거용)

    Service를 통해 범위 동기화:
    - SyncGuard를 통해 중복 실행 방지
    """
    async with get_async_db() as session:
        service = HolidayService(session)
        await service.sync_holidays_for_year(start_year, end_year, force_update=True)

