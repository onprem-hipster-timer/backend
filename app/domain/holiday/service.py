"""
Holiday Service

FastAPI Best Practices:
- Service는 비즈니스 로직을 담당
- CRUD 함수를 직접 사용 (Repository 패턴 제거)
- API 클라이언트를 사용하여 외부 API 호출
- Domain Exception을 발생시켜 비즈니스 규칙 위반 표현
"""
import asyncio
import hashlib
import json
import logging
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Session

from app.crud import holiday as crud
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
        query = HolidayQuery(solYear=year, numOfRows=num_of_rows)
        # 모든 페이지를 자동으로 가져오는 메서드 사용
        domain_items = await self.api_client.fetch_all_holidays(query)

        logger.info(
            f"Retrieved {len(domain_items)} holidays (all types) for year {year}"
        )

        return domain_items

    async def get_rest_days_by_year(self, year: int, num_of_rows: Optional[int] = None) -> List[HolidayItem]:
        """
        연도별 공휴일 정보 조회
        모든 페이지를 자동으로 가져옵니다.

        :param year: 조회 연도 (YYYY)
        :param num_of_rows: 페이지당 결과 수 (기본값: None, 100 사용)
        :return: 해당 연도의 공휴일 목록
        """
        query = HolidayQuery(solYear=year, numOfRows=num_of_rows)
        # 모든 페이지를 자동으로 가져오는 메서드 사용
        domain_items = await self.api_client.fetch_all_rest_days(query)

        logger.info(
            f"Retrieved {len(domain_items)} rest days for year {year}"
        )

        return domain_items

    async def get_anniversaries_by_year(self, year: int, num_of_rows: Optional[int] = None) -> List[HolidayItem]:
        """
        연도별 기념일 정보 조회
        모든 페이지를 자동으로 가져옵니다.

        :param year: 조회 연도 (YYYY)
        :param num_of_rows: 페이지당 결과 수 (기본값: None, 100 사용)
        :return: 해당 연도의 기념일 목록
        """
        query = HolidayQuery(solYear=year, numOfRows=num_of_rows)
        # 모든 페이지를 자동으로 가져오는 메서드 사용
        domain_items = await self.api_client.fetch_all_anniversaries(query)

        logger.info(
            f"Retrieved {len(domain_items)} anniversaries for year {year}"
        )

        return domain_items

    async def get_24divisions_by_year(self, year: int, num_of_rows: Optional[int] = None) -> List[HolidayItem]:
        """
        연도별 24절기 정보 조회
        모든 페이지를 자동으로 가져옵니다.

        :param year: 조회 연도 (YYYY)
        :param num_of_rows: 페이지당 결과 수 (기본값: None, 100 사용)
        :return: 해당 연도의 24절기 목록
        """
        query = HolidayQuery(solYear=year, numOfRows=num_of_rows)
        # 모든 페이지를 자동으로 가져오는 메서드 사용
        domain_items = await self.api_client.fetch_all_24divisions(query)

        logger.info(
            f"Retrieved {len(domain_items)} 24 divisions for year {year}"
        )

        return domain_items

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

    async def _sync_holidays_for_year_impl(
            self, year: int, force_update: bool = False
    ) -> None:
        """
        특정 연도 공휴일 동기화 실제 구현 (내부용)

        비즈니스 로직:
        - API에서 국경일, 공휴일, 기념일, 24절기 데이터 조회
        - 해시 생성 및 비교
        - 변경이 있을 때만 DB 업데이트

        :param year: 동기화할 연도
        :param force_update: True인 경우 해시 비교 없이 무조건 업데이트
        :raises Exception: 동기화 실패 시 예외 발생
        """
        # 1. 국경일, 공휴일, 기념일, 24절기 정보 조회
        national_holidays = await self.get_all_holidays_by_year(year)
        rest_days = await self.get_rest_days_by_year(year)
        anniversaries = await self.get_anniversaries_by_year(year)
        divisions_24 = await self.get_24divisions_by_year(year)

        # 2. 모든 목록을 합치고 중복 제거 (date, dateName 기준)
        # DB 유니크 제약에 의존하지 않고 메모리에서 중복 제거
        seen = set()  # (locdate, dateName) 튜플의 set
        all_holidays = []

        for holiday in national_holidays + rest_days + anniversaries + divisions_24:
            key = (holiday.locdate, holiday.dateName)
            if key not in seen:
                seen.add(key)
                all_holidays.append(holiday)

        # 3. 해시 생성
        new_hash = self.generate_hash(all_holidays)

        # 4. 기존 해시 조회 및 업데이트 건너뛰기 여부 확인
        old_hash = await crud.get_holiday_hash(self.session, year)
        if not force_update and old_hash == new_hash:
            logger.debug(f"No changes for year {year}, skipping update")
            return

        # 5. 업데이트 결정 로깅
        if force_update:
            logger.debug(
                f"Force updating holidays for {year} "
                f"(hash: {new_hash[:8]}...)"
            )
        else:
            logger.info(
                f"Holiday changes detected for {year}\n"
                f"   Old: {old_hash[:8] if old_hash else 'None'}..., "
                f"New: {new_hash[:8]}..."
            )

        # 6. DB 업데이트
        await crud.save_holidays(self.session, year, all_holidays, new_hash)

        # 중복 제거 정보 로깅
        total_count = len(national_holidays) + len(rest_days) + len(anniversaries) + len(divisions_24)
        deduplicated_count = len(all_holidays)
        if total_count != deduplicated_count:
            logger.info(
                f"Removed {total_count - deduplicated_count} duplicate holidays "
                f"before saving (total: {total_count} -> {deduplicated_count})"
            )

        logger.info(
            f"Updated {len(all_holidays)} holidays for {year} "
            f"(national: {len(national_holidays)}, rest: {len(rest_days)}, "
            f"anniversaries: {len(anniversaries)}, 24divisions: {len(divisions_24)})"
        )

    async def sync_holidays_for_year(
            self, year: int, force_update: bool = False
    ) -> None:
        """
        특정 연도 공휴일 동기화 (중복 방지 적용)

        SyncGuard를 통해 동일 연도 중복 실행 방지:
        - 이미 진행 중이면 완료를 기다림
        - 진행 중이 아니면 동기화 직접 실행

        :param year: 동기화할 연도
        :param force_update: True인 경우 해시 비교 없이 무조건 업데이트
        :raises Exception: 동기화 실패 시 예외 발생
        """
        async def _do_sync(y: int) -> None:
            """실제 동기화 수행 (SyncGuard 콜백)"""
            await self._sync_holidays_for_year_impl(y, force_update)

        await self.sync_guard.sync_year(year, _do_sync)

    async def sync_holidays_for_years(
            self, start_year: int, end_year: int, force_update: bool = False
    ) -> None:
        """
        여러 연도 공휴일 동기화 (범위 동기화, 중복 방지 적용)

        SyncGuard를 통해 각 연도별 중복 실행 방지:
        - 각 연도별로 병렬 실행
        - 모든 연도가 완료될 때까지 기다림

        :param start_year: 시작 연도
        :param end_year: 종료 연도 (포함)
        :param force_update: True인 경우 해시 비교 없이 무조건 업데이트
        :raises Exception: 동기화 실패 시 예외 발생
        """
        async def _do_sync(year: int) -> None:
            """실제 동기화 수행 (SyncGuard 콜백)"""
            await self._sync_holidays_for_year_impl(year, force_update)

        await self.sync_guard.sync_years(start_year, end_year, _do_sync)

    async def get_existing_years(self) -> set[int]:
        """
        해시 테이블에 존재하는 모든 년도 조회
        
        :return: 존재하는 년도 집합
        """
        return await crud.get_existing_years(self.session)


class HolidayReadService:
    """
    Holiday 조회 전용 서비스 (동기)

    - API 요청 시 DB 조회만 수행
    - 동기화/API 호출은 배치/백그라운드에서 처리
    """

    def __init__(self, session: Session):
        self.session = session

    def get_holidays(self, start_year: int, end_year: Optional[int] = None) -> List[HolidayItem]:
        if end_year is None:
            end_year = start_year

        models = crud.get_holidays_by_year_sync(self.session, start_year, end_year)
        return [HolidayItem.model_validate(model) for model in models]

    async def get_with_sync_option(
            self,
            start_year: int,
            end_year: Optional[int],
            sync_if_missing: bool,
    ) -> list[HolidayItem]:
        """
        조회 후, 필요 시 내부에서 비동기 동기화를 스케줄

        - 조회는 동기 세션으로 처리
        - 데이터가 없고 sync_if_missing=True이면 여기서 바로 create_task로 스케줄
        - 호출자는 반환된 조회 결과만 사용
        """
        holidays = self.get_holidays(start_year, end_year)

        if holidays or not sync_if_missing:
            return holidays

        from app.background.tasks import sync_holidays_async
        asyncio.create_task(sync_holidays_async(start_year, end_year))
        logger.info(f"Background holiday sync scheduled for years {start_year}-{end_year}")
        return holidays
