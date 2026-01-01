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
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import holiday as crud
from app.domain.holiday.client import HolidayApiClient
from app.domain.holiday.schema.dto import HolidayItem, HolidayQuery
from app.domain.holiday.exceptions import HolidayApiError, HolidayApiResponseError

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
    """

    def __init__(self, session: AsyncSession):
        """HolidayService 초기화"""
        self.session = session
        self.api_client = HolidayApiClient()

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
        # 해당 월의 국경일 조회
        holidays = await self.get_holidays_by_month(year, month)

        # 날짜 형식 변환 (YYYYMMDD)
        target_date = f"{year}{month:02d}{day:02d}"

        # 해당 날짜의 국경일 찾기
        for holiday in holidays:
            if holiday.locdate == target_date:
                return holiday.isHoliday

        return False

    async def sync_holidays_for_year(
            self, year: int, force_update: bool = False
    ) -> None:
        """
        특정 연도 공휴일 동기화 (국경일 + 공휴일 + 기념일 + 24절기)

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

    async def get_holidays(
        self, start_year: int, end_year: Optional[int] = None, num_of_rows: Optional[int] = None
    ) -> List[HolidayItem]:
        """
        DB에서 공휴일 조회, 없으면 API 호출

        비즈니스 로직:
        - 먼저 DB에서 조회 시도
        - 지정된 범위의 데이터가 없으면 API 호출하여 조회 및 저장
        - end_year가 지정되지 않으면 start_year과 동일하게 처리 (단일 연도 조회)
        - 일부 연도 API 호출 실패 시에도 성공한 연도만 반환 (부분 실패 허용)

        :param start_year: 시작 연도
        :param end_year: 종료 연도 (포함). None이면 start_year과 동일하게 처리
        :param num_of_rows: 페이지당 결과 수 (API 호출 시 사용)
        :return: 공휴일 목록 (성공한 연도만 포함)
        :raises HolidayApiError: 모든 연도가 실패한 경우
        """
        # end_year가 지정되지 않으면 start_year과 동일하게 처리
        if end_year is None:
            end_year = start_year

        # 1. DB에서 조회 시도 (CRUD 직접 호출)
        models = await crud.get_holidays_by_year(self.session, start_year, end_year)

        # Model을 DTO로 변환 (Pydantic from_attributes 사용)
        db_items = [HolidayItem.model_validate(model) for model in models]

        if db_items:
            return db_items

        # 2. DB에 데이터가 없으면 API 호출하여 모든 연도 동기화
        # sync_holidays_for_year가 내부에서 모든 API 호출 및 로깅을 처리
        # 일부 연도 실패 시에도 성공한 연도만 저장하고 계속 진행
        successful_years = []
        failed_years = []

        for year in range(start_year, end_year + 1):
            try:
                await self.sync_holidays_for_year(year, force_update=True)
                successful_years.append(year)
            except (HolidayApiError, HolidayApiResponseError) as e:
                failed_years.append(year)
                logger.warning(
                    f"Failed to sync holidays for year {year}: {str(e)}. "
                    f"Continuing with other years."
                )
            except Exception as e:
                # 예상치 못한 예외도 로깅하고 계속 진행
                failed_years.append(year)
                logger.error(
                    f"Unexpected error while syncing holidays for year {year}: {str(e)}. "
                    f"Continuing with other years.",
                    exc_info=True
                )

        # 성공한 연도가 하나라도 있으면 commit
        if successful_years:
            await self.session.commit()

            if failed_years:
                logger.warning(
                    f"Partially succeeded: {len(successful_years)} years succeeded, "
                    f"{len(failed_years)} years failed (years: {failed_years})"
                )
        else:
            # 모든 연도가 실패한 경우
            logger.error(
                f"All years failed to sync (range: {start_year}-{end_year})"
            )
            # commit하지 않고 예외를 다시 발생시켜 호출자가 알 수 있도록
            if start_year == end_year:
                raise HolidayApiError(
                    f"Failed to fetch holiday information for year {start_year}"
                )
            else:
                raise HolidayApiError(
                    f"Failed to fetch holiday information for all years in range {start_year}-{end_year}"
                )

        # 동기화 후 다시 DB에서 조회하여 반환 (성공한 연도만 포함)
        models = await crud.get_holidays_by_year(self.session, start_year, end_year)
        return [HolidayItem.model_validate(model) for model in models]
