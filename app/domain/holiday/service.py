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
        # JSON 직렬화 (정렬 필수 - 일관성 보장)
        holidays_json = json.dumps(
            [h.model_dump() for h in holidays],
            sort_keys=True,
            default=str,  # datetime 등 처리
            ensure_ascii=False,  # 한글 깨짐 방지
        )
        
        # SHA256 해시 생성
        holiday_hash = hashlib.sha256(
            holidays_json.encode('utf-8')
        ).hexdigest()
        
        return holiday_hash

    async def get_holidays(self, query: HolidayQuery) -> List[HolidayItem]:
        """
        국경일 정보 조회
        
        비즈니스 로직:
        - 연·월 단위로 국경일 정보 조회
        - dateKind == "01"인 데이터만 반환 (국경일만)
        - isHoliday로 실제 휴일 여부 확인 가능
        
        :param query: 조회 요청 데이터 (solYear, solMonth, numOfRows)
        :return: 국경일 목록
        :raises HolidayApiError: API 호출 실패
        :raises HolidayApiResponseError: API 응답 오류
        """
        # API 호출
        api_response = await self.api_client.fetch_holidays(query)
        
        # API 응답을 도메인 DTO로 변환
        domain_items = api_response.to_domain_items()
        
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
        return await self.get_holidays(query)
    
    async def get_all_holidays_by_year(self, year: int, num_of_rows: Optional[int] = None) -> List[HolidayItem]:
        """
        연도별 모든 특일 정보 조회 (국경일, 기념일, 24절기, 잡절 모두)
        
        :param year: 조회 연도 (YYYY)
        :param num_of_rows: 페이지당 결과 수 (기본값: None, API 기본값 사용)
        :return: 해당 연도의 모든 특일 목록
        """
        query = HolidayQuery(solYear=year, numOfRows=num_of_rows)
        # API 호출
        api_response = await self.api_client.fetch_holidays(query)
        
        # API 응답을 도메인 DTO로 변환 (모든 dateKind 포함)
        domain_items = api_response.to_domain_items()
        
        logger.info(
            f"Retrieved {len(domain_items)} holidays (all types) for year {year}"
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
        return await self.get_holidays(query)

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
                return holiday.is_holiday_bool
        
        return False
    
    async def sync_holidays_for_year(
        self, year: int, force_update: bool = False
    ) -> None:
        """
        특정 연도 공휴일 동기화
        
        비즈니스 로직:
        - API에서 데이터 조회
        - 해시 생성 및 비교
        - 변경이 있을 때만 DB 업데이트
        
        :param year: 동기화할 연도
        :param force_update: True인 경우 해시 비교 없이 무조건 업데이트
        :raises Exception: 동기화 실패 시 예외 발생
        """
        # 1. 모든 특일 정보 조회 및 해시 생성
        holidays = await self.get_all_holidays_by_year(year)
        new_hash = self.generate_hash(holidays)
        
        # 2. 기존 해시 조회 및 업데이트 건너뛰기 여부 확인
        old_hash = await crud.get_holiday_hash(self.session, year)
        if not force_update and old_hash == new_hash:
            logger.debug(f"No changes for year {year}, skipping update")
            return
        
        # 3. 업데이트 결정 로깅
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
        
        # 4. DB 업데이트
        await crud.save_holidays(self.session, year, holidays, new_hash)
        logger.info(f"Updated {len(holidays)} holidays for {year}")

