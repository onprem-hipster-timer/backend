"""
Holiday Service

FastAPI Best Practices:
- Service는 비즈니스 로직을 담당
- CRUD 함수를 직접 사용 (Repository 패턴 제거)
- API 클라이언트를 사용하여 외부 API 호출
- Domain Exception을 발생시켜 비즈니스 규칙 위반 표현
"""
import hashlib
import json
import logging
from typing import Awaitable, Callable, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Session

from app.crud import holiday as crud
from app.domain.holiday import logger as domain_log
from app.domain.holiday.client import HolidayApiClient
from app.domain.holiday.schema.dto import HolidayItem, HolidayQuery
from app.domain.holiday.sync_guard import get_sync_guard

logger = logging.getLogger(__name__)


class HolidayService:
    """
    Holiday Service - 국경일 정보 조회 비즈니스 로직

    한국천문연구원 특일 정보제공 서비스(OpenAPI)를 활용하여
    국경일 정보를 조회하고 동기화합니다.

    FastAPI Best Practices:
    - Repository 패턴 제거, CRUD 함수 직접 사용
    - Session을 받아서 CRUD 함수 호출
    - 비즈니스 로직 담당 (해시 비교, 동기화 로직 등)
    - SyncGuard를 통한 중복 방지 (모든 호출 경로에서 자동 적용)
    """

    def __init__(self, session: AsyncSession):
        """HolidayService 초기화"""
        self.session = session
        self.api_client = HolidayApiClient()
        self.sync_guard = get_sync_guard()

    @staticmethod
    def generate_hash(holidays: List[HolidayItem]) -> str:
        """
        공휴일 목록의 해시 생성

        :param holidays: 공휴일 목록
        :return: SHA256 해시
        """
        # 리스트를 정렬하여 순서에 무관하게 동일한 해시 생성
        # locdate와 dateName을 기준으로 정렬 (여러 페이지 조회 시에도 일관성 보장)
        sorted_holidays = sorted(
            holidays,
            key=lambda h: (h.locdate, h.dateName)
        )

        # JSON 직렬화 (정렬 필수 - 일관성 보장)
        holidays_json = json.dumps(
            [h.model_dump() for h in sorted_holidays],
            sort_keys=True,
            default=str,  # datetime 등 처리
            ensure_ascii=False,  # 한글 깨짐 방지
        )

        # SHA256 해시 생성
        holiday_hash = hashlib.sha256(
            holidays_json.encode('utf-8')
        ).hexdigest()

        return holiday_hash

    async def get_holidays_from_api(self, query: HolidayQuery) -> List[HolidayItem]:
        """
        API에서 국경일 정보 조회
        모든 페이지를 자동으로 가져옵니다.

        비즈니스 로직:
        - 연·월 단위로 국경일 정보 조회
        - dateKind == "01"인 데이터만 반환 (국경일만)
        - isHoliday로 실제 휴일 여부 확인 가능

        :param query: 조회 요청 데이터 (solYear, solMonth, numOfRows)
        :return: 국경일 목록
        :raises HolidayApiError: API 호출 실패
        :raises HolidayApiResponseError: API 응답 오류
        """
        # 모든 페이지를 자동으로 가져오는 메서드 사용
        domain_items = await self.api_client.fetch_all_holidays(query)

        # 국경일 목록 반환 (dateKind == "01"인 것만)
        national_holidays = [item for item in domain_items if item.is_national_holiday]

        month_info = f", month {query.solMonth}" if query.solMonth else ""
        logger.info(
            f"Retrieved {len(national_holidays)} national holidays "
            f"for year {query.solYear}{month_info}"
        )

        return national_holidays

    async def _fetch_by_year(
            self,
            year: int,
            fetch_func: Callable[[HolidayQuery], Awaitable[List[HolidayItem]]],
            data_type_name: str,
            num_of_rows: Optional[int] = None,
    ) -> List[HolidayItem]:
        """
        연도별 데이터 조회 공통 로직

        :param year: 조회 연도 (YYYY)
        :param fetch_func: API 클라이언트의 fetch 함수
        :param data_type_name: 로깅용 데이터 타입 이름
        :param num_of_rows: 페이지당 결과 수 (기본값: None)
        :return: HolidayItem 리스트
        """
        query = HolidayQuery(solYear=year, numOfRows=num_of_rows)
        domain_items = await fetch_func(query)
        logger.info(f"Retrieved {len(domain_items)} {data_type_name} for year {year}")
        return domain_items

    async def get_holidays_by_year(self, year: int, num_of_rows: Optional[int] = None) -> List[HolidayItem]:
        """
        연도별 국경일 정보 조회 (국경일만)

        :param year: 조회 연도 (YYYY)
        :param num_of_rows: 페이지당 결과 수 (기본값: None, API 기본값 사용)
        :return: 해당 연도의 국경일 목록
        """
        query = HolidayQuery(solYear=year, numOfRows=num_of_rows)
        return await self.get_holidays_from_api(query)

    async def get_all_holidays_by_year(self, year: int, num_of_rows: Optional[int] = None) -> List[HolidayItem]:
        """
        연도별 모든 특일 정보 조회 (국경일, 기념일, 24절기, 잡절 모두)
        모든 페이지를 자동으로 가져옵니다.

        :param year: 조회 연도 (YYYY)
        :param num_of_rows: 페이지당 결과 수 (기본값: None, 100 사용)
        :return: 해당 연도의 모든 특일 목록
        """
        return await self._fetch_by_year(
            year,
            self.api_client.fetch_all_holidays,
            "holidays (all types)",
            num_of_rows
        )

    async def get_rest_days_by_year(self, year: int, num_of_rows: Optional[int] = None) -> List[HolidayItem]:
        """
        연도별 공휴일 정보 조회
        모든 페이지를 자동으로 가져옵니다.

        :param year: 조회 연도 (YYYY)
        :param num_of_rows: 페이지당 결과 수 (기본값: None, 100 사용)
        :return: 해당 연도의 공휴일 목록
        """
        return await self._fetch_by_year(
            year,
            self.api_client.fetch_all_rest_days,
            "rest days",
            num_of_rows
        )

    async def get_anniversaries_by_year(self, year: int, num_of_rows: Optional[int] = None) -> List[HolidayItem]:
        """
        연도별 기념일 정보 조회
        모든 페이지를 자동으로 가져옵니다.

        :param year: 조회 연도 (YYYY)
        :param num_of_rows: 페이지당 결과 수 (기본값: None, 100 사용)
        :return: 해당 연도의 기념일 목록
        """
        return await self._fetch_by_year(
            year,
            self.api_client.fetch_all_anniversaries,
            "anniversaries",
            num_of_rows
        )

    async def get_24divisions_by_year(self, year: int, num_of_rows: Optional[int] = None) -> List[HolidayItem]:
        """
        연도별 24절기 정보 조회
        모든 페이지를 자동으로 가져옵니다.

        :param year: 조회 연도 (YYYY)
        :param num_of_rows: 페이지당 결과 수 (기본값: None, 100 사용)
        :return: 해당 연도의 24절기 목록
        """
        return await self._fetch_by_year(
            year,
            self.api_client.fetch_all_24divisions,
            "24 divisions",
            num_of_rows
        )

    async def get_holidays_by_month(
            self, year: int, month: int, num_of_rows: Optional[int] = None
    ) -> List[HolidayItem]:
        """
        연월별 국경일 정보 조회

        :param year: 조회 연도 (YYYY)
        :param month: 조회 월 (MM)
        :param num_of_rows: 페이지당 결과 수 (기본값: None, API 기본값 사용)
        :return: 해당 연월의 국경일 목록
        """
        query = HolidayQuery(solYear=year, solMonth=month, numOfRows=num_of_rows)
        return await self.get_holidays_from_api(query)

    async def is_holiday(self, year: int, month: int, day: int) -> bool:
        """
        특정 날짜가 공휴일인지 확인

        :param year: 연도 (YYYY)
        :param month: 월 (MM)
        :param day: 일 (DD)
        :return: 공휴일이면 True, 아니면 False
        """
        from app.domain.dateutil.service import parse_locdate_to_datetime_range
        from app.crud import holiday as crud

        # 날짜 형식 변환 (YYYYMMDD)
        target_date_str = f"{year}{month:02d}{day:02d}"

        # 한국 표준시 기준 날짜 범위로 변환
        start_date, end_date = parse_locdate_to_datetime_range(target_date_str)

        # 범위 내에 포함되는 공휴일 조회 (start_date를 기준으로 조회)
        # 실제로는 start_date가 범위 내에 있는지 확인해야 하므로
        # DB에서 직접 조회하는 것이 더 정확함
        holiday = await crud.get_holiday_by_date(self.session, start_date)

        return holiday.isHoliday if holiday else False

    # ============ 동기화 관련 메서드 ============

    async def _fetch_all_holidays_for_year(self, year: int) -> dict[str, List[HolidayItem]]:
        """
        API에서 모든 종류의 공휴일 데이터 조회
        
        :param year: 조회 연도
        :return: 종류별 공휴일 딕셔너리
        """
        return {
            "national": await self.get_all_holidays_by_year(year),
            "rest": await self.get_rest_days_by_year(year),
            "anniversaries": await self.get_anniversaries_by_year(year),
            "divisions_24": await self.get_24divisions_by_year(year),
        }

    @staticmethod
    def _deduplicate_holidays(holidays_by_type: dict[str, List[HolidayItem]]) -> List[HolidayItem]:
        """
        중복 공휴일 제거 (locdate, dateName 기준)
        
        :param holidays_by_type: 종류별 공휴일 딕셔너리
        :return: 중복 제거된 공휴일 리스트
        """
        seen: set[tuple[str, str]] = set()
        deduplicated: List[HolidayItem] = []

        all_holidays = (
                holidays_by_type["national"] +
                holidays_by_type["rest"] +
                holidays_by_type["anniversaries"] +
                holidays_by_type["divisions_24"]
        )

        for holiday in all_holidays:
            key = (holiday.locdate, holiday.dateName)
            if key not in seen:
                seen.add(key)
                deduplicated.append(holiday)

        return deduplicated

    async def _should_update(
            self, year: int, new_hash: str, force_update: bool
    ) -> tuple[bool, Optional[str]]:
        """
        해시 비교하여 업데이트 필요 여부 확인
        
        :param year: 연도
        :param new_hash: 새 해시값
        :param force_update: 강제 업데이트 여부
        :return: (업데이트 필요 여부, 기존 해시값)
        """
        old_hash = await crud.get_holiday_hash(self.session, year)

        if force_update:
            return True, old_hash

        return old_hash != new_hash, old_hash

    async def sync_holidays_for_year(
            self,
            year: int,
            end_year: Optional[int] = None,
            force_update: bool = False
    ) -> None:
        """
        공휴일 동기화 (중복 방지 적용)

        SyncGuard를 통해 동일 연도 중복 실행 방지:
        - 이미 진행 중이면 완료를 기다림
        - 진행 중이 아니면 동기화 직접 실행

        :param year: 동기화할 연도 (또는 시작 연도)
        :param end_year: 종료 연도 (포함). None이면 year만 동기화
        :param force_update: True인 경우 해시 비교 없이 무조건 업데이트
        :raises Exception: 동기화 실패 시 예외 발생
        """

        async def _do_sync(y: int) -> None:
            # 1. API에서 데이터 조회
            holidays_by_type = await self._fetch_all_holidays_for_year(y)

            # 2. 중복 제거
            deduplicated = self._deduplicate_holidays(holidays_by_type)

            # 3. 해시 생성 및 비교
            new_hash = self.generate_hash(deduplicated)
            should_update, old_hash = await self._should_update(y, new_hash, force_update)

            if not should_update:
                logger.debug(f"No changes for year {y}, skipping update")
                return

            # 4. DB 저장
            await crud.save_holidays(self.session, y, deduplicated, new_hash)

            # 5. 로깅
            domain_log.log_sync_result(y, holidays_by_type, deduplicated, new_hash, old_hash, force_update)

        await self.sync_guard.sync_year(year, _do_sync, end_year=end_year)

    async def get_existing_years(self) -> set[int]:
        """
        해시 테이블에 존재하는 모든 년도 조회
        
        :return: 존재하는 년도 집합
        """
        return await crud.get_existing_years(self.session)

    def _filter_missing_years(
            self, existing_years: set[int], start_year: int, end_year: int
    ) -> tuple[list[int], int]:
        """
        존재하지 않는 연도 필터링
        
        :param existing_years: 이미 존재하는 연도 집합
        :param start_year: 시작 연도
        :param end_year: 종료 연도 (포함)
        :return: (동기화할 연도 리스트, 건너뛴 연도 수)
        """
        all_years = list(range(start_year, end_year + 1))
        missing_years = [y for y in all_years if y not in existing_years]
        skipped_count = len(all_years) - len(missing_years)
        return missing_years, skipped_count

    async def initialize_historical_data(
            self, initial_year: int, current_year: int
    ) -> bool:
        """
        초기 데이터 로드: initial_year부터 current_year까지 모든 연도 동기화
        
        서버 처음 실행 시:
        - 해시 테이블에 이미 존재하는 년도는 건너뜀
        - 존재하지 않는 년도만 동기화
        
        :param initial_year: 시작 연도
        :param current_year: 현재 연도
        :return: 초기화 작업이 수행되었으면 True, 이미 완료되었으면 False
        :raises Exception: 동기화 실패 시 예외 발생
        """
        existing_years = await self.get_existing_years()
        years_to_initialize, skipped_count = self._filter_missing_years(
            existing_years, initial_year, current_year
        )

        domain_log.log_initialization_skipped(skipped_count, existing_years)

        if not years_to_initialize:
            domain_log.log_initialization_not_needed(initial_year, current_year)
            return False

        total_years = len(years_to_initialize)
        domain_log.log_initialization_start(initial_year, current_year, total_years, skipped_count)

        for idx, year in enumerate(years_to_initialize, 1):
            await self.sync_holidays_for_year(year, force_update=True)
            domain_log.log_initialization_progress(year, idx, total_years)

        domain_log.log_initialization_complete(total_years)
        return True

    async def sync_current_and_next_year(self) -> None:
        """
        현재 연도 + 내년 공휴일 동기화 (정기 동기화용)
        
        백그라운드 태스크에서 주기적으로 호출하여 최신 데이터 유지
        로깅은 sync_holidays_for_year가 처리
        """
        from datetime import datetime
        current_year = datetime.now().year
        await self.sync_holidays_for_year(current_year, current_year + 1)


class HolidayReadService:
    """
    Holiday 조회 전용 서비스 (동기)

    - API 요청 시 DB 조회만 수행
    - 동기화/API 호출은 배치/백그라운드에서 처리
    """

    def __init__(self, session: Session):
        self.session = session

    def get_holidays(
            self,
            start_year: int,
            end_year: Optional[int] = None,
            auto_sync: bool = False
    ) -> List[HolidayItem]:
        """
        공휴일 조회 (DB에 있는 데이터만 반환)

        :param start_year: 시작 연도
        :param end_year: 종료 연도 (None이면 start_year와 동일)
        :param auto_sync: 데이터가 없을 경우 자동으로 동기화 태스크 스케줄
        :return: 공휴일 목록
        """
        if end_year is None:
            end_year = start_year

        models = crud.get_holidays_by_year_sync(self.session, start_year, end_year)
        holidays = [HolidayItem.model_validate(model) for model in models]

        # 데이터가 없고 auto_sync=True이면 백그라운드 동기화 태스크 스케줄
        if not holidays and auto_sync:
            import asyncio
            from app.domain.holiday.tasks import sync_holidays_async
            asyncio.create_task(sync_holidays_async(start_year, end_year))
            logger.info(f"Background holiday sync scheduled for years {start_year}-{end_year}")

        return holidays
