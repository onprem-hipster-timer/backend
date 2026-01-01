"""
Holiday Service

FastAPI Best Practices:
- Service는 비즈니스 로직을 담당
- 외부 API 호출 로직 포함
- Domain Exception을 발생시켜 비즈니스 규칙 위반 표현
"""
import logging
from typing import List, Optional

import httpx

from app.core.config import settings
from app.domain.holiday.exceptions import (
    HolidayApiError,
    HolidayApiKeyError,
    HolidayApiResponseError,
)
from app.domain.holiday.schema.dto import HolidayItem, HolidayQuery, HolidayResponse

logger = logging.getLogger(__name__)


class HolidayService:
    """
    Holiday Service - 국경일 정보 조회
    
    한국천문연구원 특일 정보제공 서비스(OpenAPI)를 활용하여
    국경일 정보를 조회합니다.
    
    FastAPI Best Practices:
    - 외부 API 호출 로직 포함
    - Domain Exception을 발생시켜 오류 표현
    - httpx를 사용한 비동기 HTTP 클라이언트
    """

    BASE_URL = settings.HOLIDAY_API_BASE_URL
    ENDPOINT = "/getHoliDeInfo"

    def __init__(self):
        """HolidayService 초기화"""
        if not settings.HOLIDAY_API_SERVICE_KEY:
            raise HolidayApiKeyError("Holiday API service key is not configured")

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
        try:
            # API 요청 파라미터 준비
            params = {
                "solYear": str(query.solYear),
                "ServiceKey": settings.HOLIDAY_API_SERVICE_KEY,
                "_type": "json",  # JSON 응답 요청
            }

            if query.solMonth is not None:
                params["solMonth"] = f"{query.solMonth:02d}"  # MM 형식

            if query.numOfRows is not None:
                params["numOfRows"] = str(query.numOfRows)

            # API 호출
            url = f"{self.BASE_URL}{self.ENDPOINT}"
            logger.info(f"Calling holiday API: {url} with params: {dict(params, ServiceKey='***')}")

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()

                # JSON 응답 파싱
                data = response.json()
                
                # API 응답 구조: {"response": {...}} 또는 직접 {...}
                if "response" in data:
                    data = data["response"]
                
                holiday_response = HolidayResponse(**data)

                # 응답 코드 확인
                if not holiday_response.is_success:
                    error_msg = f"API returned error: {holiday_response.header.resultMsg}"
                    logger.error(error_msg)
                    raise HolidayApiResponseError(error_msg)

                # 국경일 목록 반환 (dateKind == "01"인 것만)
                items = holiday_response.items
                national_holidays = [item for item in items if item.is_national_holiday]

                month_info = f", month {query.solMonth}" if query.solMonth else ""
                logger.info(
                    f"Retrieved {len(national_holidays)} national holidays "
                    f"for year {query.solYear}{month_info}"
                )

                return national_holidays

        except httpx.HTTPError as e:
            logger.error(f"HTTP error when calling holiday API: {str(e)}")
            raise HolidayApiError(f"Failed to fetch holiday information: {str(e)}")
        except KeyError as e:
            logger.error(f"Missing key in API response: {str(e)}")
            raise HolidayApiResponseError(f"Invalid API response format: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error when calling holiday API: {str(e)}")
            raise HolidayApiError(f"Unexpected error: {str(e)}")

    async def get_holidays_by_year(self, year: int, num_of_rows: Optional[int] = None) -> List[HolidayItem]:
        """
        연도별 국경일 정보 조회
        
        :param year: 조회 연도 (YYYY)
        :param num_of_rows: 페이지당 결과 수 (기본값: None, API 기본값 사용)
        :return: 해당 연도의 국경일 목록
        """
        query = HolidayQuery(solYear=year, numOfRows=num_of_rows)
        return await self.get_holidays(query)

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

