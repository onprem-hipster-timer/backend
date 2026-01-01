"""
Holiday API Client

외부 API 호출 전담 클래스
한국천문연구원 특일 정보제공 서비스(OpenAPI)와의 통신 담당

객체지향 원칙 준수:
- Single Responsibility: 각 메서드는 하나의 책임만 담당
- 메서드 분리로 재사용성 및 테스트 용이성 향상
"""
import logging
from typing import Dict, Any, List

import httpx

from app.core.config import settings
from app.domain.holiday.exceptions import (
    HolidayApiError,
    HolidayApiKeyError,
    HolidayApiResponseError,
)
from app.domain.holiday.schema.dto import HolidayQuery, HolidayApiResponse, HolidayItem

logger = logging.getLogger(__name__)


class HolidayApiClient:
    """
    국경일 및 공휴일 정보 API 클라이언트
    
    외부 API 호출 및 응답 파싱 전담
    """

    BASE_URL = settings.HOLIDAY_API_BASE_URL
    NATIONAL_HOLIDAY_ENDPOINT = "/getHoliDeInfo"  # 국경일 정보 조회
    REST_DAY_ENDPOINT = "/getRestDeInfo"  # 공휴일 정보 조회
    ANNIVERSARY_ENDPOINT = "/getAnniversaryInfo"  # 기념일 정보 조회
    DIVISIONS_24_ENDPOINT = "/get24DivisionsInfo"  # 24절기 정보 조회
    TIMEOUT = 10.0

    def __init__(self):
        """HolidayApiClient 초기화"""
        if not settings.HOLIDAY_API_SERVICE_KEY:
            raise HolidayApiKeyError("Holiday API service key is not configured")

    def _build_params(self, query: HolidayQuery) -> Dict[str, str]:
        """
        API 요청 파라미터 구성
        
        :param query: 조회 요청 데이터
        :return: 요청 파라미터 딕셔너리
        """
        params = {
            "solYear": str(query.solYear),
            "ServiceKey": settings.HOLIDAY_API_SERVICE_KEY,
            "_type": "json",  # JSON 응답 요청
        }

        if query.solMonth is not None:
            params["solMonth"] = f"{query.solMonth:02d}"  # MM 형식

        if query.numOfRows is not None:
            params["numOfRows"] = str(query.numOfRows)

        if query.pageNo is not None:
            params["pageNo"] = str(query.pageNo)

        return params

    def _build_url(self, endpoint: str) -> str:
        """
        API 요청 URL 구성
        
        :param endpoint: API 엔드포인트
        :return: 완전한 API URL
        """
        return f"{self.BASE_URL}{endpoint}"

    async def _make_request(self, url: str, params: Dict[str, str]) -> Dict[str, Any]:
        """
        HTTP 요청 실행
        
        :param url: 요청 URL
        :param params: 요청 파라미터
        :return: JSON 응답 데이터
        :raises HolidayApiError: HTTP 요청 실패
        """
        try:
            logger.info(f"Calling holiday API: {url} with params: {dict(params, ServiceKey='***')}")

            async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response.json()

        except httpx.HTTPError as e:
            logger.error(f"HTTP error when calling holiday API: {str(e)}")
            raise HolidayApiError(f"Failed to fetch holiday information: {str(e)}")

    def _normalize_response_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        API 응답 데이터 정규화
        
        {"response": {...}} 구조를 {...}로 변환
        
        :param data: 원본 응답 데이터
        :return: 정규화된 응답 데이터
        """
        if "response" in data:
            return data["response"]
        return data

    def _parse_response(self, data: Dict[str, Any]) -> HolidayApiResponse:
        """
        응답 데이터를 HolidayApiResponse로 파싱
        
        :param data: 정규화된 응답 데이터
        :return: 파싱된 API 응답 객체
        :raises HolidayApiResponseError: 파싱 실패
        """
        try:
            return HolidayApiResponse(**data)
        except (KeyError, TypeError) as e:
            logger.error(f"Failed to parse API response: {str(e)}")
            raise HolidayApiResponseError(f"Invalid API response format: {str(e)}")

    def _validate_response(self, api_response: HolidayApiResponse) -> HolidayApiResponse:
        """
        API 응답 검증
        
        :param api_response: API 응답 객체
        :return: 검증된 API 응답 객체
        :raises HolidayApiResponseError: 응답 오류
        """
        if not api_response.is_success:
            error_msg = f"API returned error: {api_response.header.resultMsg}"
            logger.error(error_msg)
            raise HolidayApiResponseError(error_msg)
        return api_response

    async def _fetch_holidays_page(self, query: HolidayQuery) -> HolidayApiResponse:
        """
        API에서 국경일 정보 조회 (단일 페이지)
        
        내부 메서드: fetch_all_holidays()에서 사용
        
        :param query: 조회 요청 데이터 (solYear, solMonth, numOfRows, pageNo)
        :return: API 응답 객체
        :raises HolidayApiError: API 호출 실패
        :raises HolidayApiResponseError: API 응답 오류
        """
        return self._validate_response(
            self._parse_response(
                self._normalize_response_data(
                    await self._make_request(
                        self._build_url(self.NATIONAL_HOLIDAY_ENDPOINT),
                        self._build_params(query)
                    )
                )
            )
        )

    async def _fetch_rest_days_page(self, query: HolidayQuery) -> HolidayApiResponse:
        """
        API에서 공휴일 정보 조회 (단일 페이지)
        
        내부 메서드: fetch_all_rest_days()에서 사용
        
        :param query: 조회 요청 데이터 (solYear, solMonth, numOfRows, pageNo)
        :return: API 응답 객체
        :raises HolidayApiError: API 호출 실패
        :raises HolidayApiResponseError: API 응답 오류
        """
        return self._validate_response(
            self._parse_response(
                self._normalize_response_data(
                    await self._make_request(
                        self._build_url(self.REST_DAY_ENDPOINT),
                        self._build_params(query)
                    )
                )
            )
        )

    async def fetch_all_holidays(self, query: HolidayQuery) -> List[HolidayItem]:
        """
        모든 페이지의 국경일 정보를 조회하여 합쳐서 반환
        
        :param query: 조회 요청 데이터 (solYear, solMonth, numOfRows)
        :return: 모든 페이지의 국경일 목록
        :raises HolidayApiError: API 호출 실패
        :raises HolidayApiResponseError: API 응답 오류
        """
        # 첫 번째 페이지 조회 (totalCount 확인용)
        first_query = HolidayQuery(
            solYear=query.solYear,
            solMonth=query.solMonth,
            numOfRows=query.numOfRows or 100,  # 기본값 100으로 설정하여 페이지 수 최소화
            pageNo=1
        )
        first_response = await self._fetch_holidays_page(first_query)
        all_items = first_response.to_domain_items()

        total_count = first_response.body.totalCount or 0
        num_of_rows = first_query.numOfRows or 100

        # totalCount가 numOfRows보다 크면 추가 페이지 조회
        if total_count > num_of_rows:
            total_pages = (total_count + num_of_rows - 1) // num_of_rows  # 올림 계산

            logger.info(
                f"Fetching all pages for holidays: "
                f"totalCount={total_count}, numOfRows={num_of_rows}, totalPages={total_pages}"
            )

            # 나머지 페이지들 조회
            for page_no in range(2, total_pages + 1):
                page_query = HolidayQuery(
                    solYear=query.solYear,
                    solMonth=query.solMonth,
                    numOfRows=num_of_rows,
                    pageNo=page_no
                )
                page_response = await self._fetch_holidays_page(page_query)
                all_items.extend(page_response.to_domain_items())
                logger.debug(f"Fetched page {page_no}/{total_pages} for holidays")

        logger.info(f"Fetched total {len(all_items)} holidays from all pages")
        return all_items

    async def fetch_all_rest_days(self, query: HolidayQuery) -> List[HolidayItem]:
        """
        모든 페이지의 공휴일 정보를 조회하여 합쳐서 반환
        
        :param query: 조회 요청 데이터 (solYear, solMonth, numOfRows)
        :return: 모든 페이지의 공휴일 목록
        :raises HolidayApiError: API 호출 실패
        :raises HolidayApiResponseError: API 응답 오류
        """
        # 첫 번째 페이지 조회 (totalCount 확인용)
        first_query = HolidayQuery(
            solYear=query.solYear,
            solMonth=query.solMonth,
            numOfRows=query.numOfRows or 100,  # 기본값 100으로 설정하여 페이지 수 최소화
            pageNo=1
        )
        first_response = await self._fetch_rest_days_page(first_query)
        all_items = first_response.to_domain_items()

        total_count = first_response.body.totalCount or 0
        num_of_rows = first_query.numOfRows or 100

        # totalCount가 numOfRows보다 크면 추가 페이지 조회
        if total_count > num_of_rows:
            total_pages = (total_count + num_of_rows - 1) // num_of_rows  # 올림 계산

            logger.info(
                f"Fetching all pages for rest days: "
                f"totalCount={total_count}, numOfRows={num_of_rows}, totalPages={total_pages}"
            )

            # 나머지 페이지들 조회
            for page_no in range(2, total_pages + 1):
                page_query = HolidayQuery(
                    solYear=query.solYear,
                    solMonth=query.solMonth,
                    numOfRows=num_of_rows,
                    pageNo=page_no
                )
                page_response = await self._fetch_rest_days_page(page_query)
                all_items.extend(page_response.to_domain_items())
                logger.debug(f"Fetched page {page_no}/{total_pages} for rest days")

        logger.info(f"Fetched total {len(all_items)} rest days from all pages")
        return all_items

    async def _fetch_anniversary_page(self, query: HolidayQuery) -> HolidayApiResponse:
        """
        API에서 기념일 정보 조회 (단일 페이지)
        
        내부 메서드: fetch_all_anniversaries()에서 사용
        
        :param query: 조회 요청 데이터 (solYear, solMonth, numOfRows, pageNo)
        :return: API 응답 객체
        :raises HolidayApiError: API 호출 실패
        :raises HolidayApiResponseError: API 응답 오류
        """
        return self._validate_response(
            self._parse_response(
                self._normalize_response_data(
                    await self._make_request(
                        self._build_url(self.ANNIVERSARY_ENDPOINT),
                        self._build_params(query)
                    )
                )
            )
        )

    async def _fetch_24divisions_page(self, query: HolidayQuery) -> HolidayApiResponse:
        """
        API에서 24절기 정보 조회 (단일 페이지)
        
        내부 메서드: fetch_all_24divisions()에서 사용
        
        :param query: 조회 요청 데이터 (solYear, solMonth, numOfRows, pageNo)
        :return: API 응답 객체
        :raises HolidayApiError: API 호출 실패
        :raises HolidayApiResponseError: API 응답 오류
        """
        return self._validate_response(
            self._parse_response(
                self._normalize_response_data(
                    await self._make_request(
                        self._build_url(self.DIVISIONS_24_ENDPOINT),
                        self._build_params(query)
                    )
                )
            )
        )

    async def fetch_all_anniversaries(self, query: HolidayQuery) -> List[HolidayItem]:
        """
        모든 페이지의 기념일 정보를 조회하여 합쳐서 반환
        
        :param query: 조회 요청 데이터 (solYear, solMonth, numOfRows)
        :return: 모든 페이지의 기념일 목록
        :raises HolidayApiError: API 호출 실패
        :raises HolidayApiResponseError: API 응답 오류
        """
        # 첫 번째 페이지 조회 (totalCount 확인용)
        first_query = HolidayQuery(
            solYear=query.solYear,
            solMonth=query.solMonth,
            numOfRows=query.numOfRows or 100,  # 기본값 100으로 설정하여 페이지 수 최소화
            pageNo=1
        )
        first_response = await self._fetch_anniversary_page(first_query)
        all_items = first_response.to_domain_items()

        total_count = first_response.body.totalCount or 0
        num_of_rows = first_query.numOfRows or 100

        # totalCount가 numOfRows보다 크면 추가 페이지 조회
        if total_count > num_of_rows:
            total_pages = (total_count + num_of_rows - 1) // num_of_rows  # 올림 계산

            logger.info(
                f"Fetching all pages for anniversaries: "
                f"totalCount={total_count}, numOfRows={num_of_rows}, totalPages={total_pages}"
            )

            # 나머지 페이지들 조회
            for page_no in range(2, total_pages + 1):
                page_query = HolidayQuery(
                    solYear=query.solYear,
                    solMonth=query.solMonth,
                    numOfRows=num_of_rows,
                    pageNo=page_no
                )
                page_response = await self._fetch_anniversary_page(page_query)
                all_items.extend(page_response.to_domain_items())
                logger.debug(f"Fetched page {page_no}/{total_pages} for anniversaries")

        logger.info(f"Fetched total {len(all_items)} anniversaries from all pages")
        return all_items

    async def fetch_all_24divisions(self, query: HolidayQuery) -> List[HolidayItem]:
        """
        모든 페이지의 24절기 정보를 조회하여 합쳐서 반환
        
        :param query: 조회 요청 데이터 (solYear, solMonth, numOfRows)
        :return: 모든 페이지의 24절기 목록
        :raises HolidayApiError: API 호출 실패
        :raises HolidayApiResponseError: API 응답 오류
        """
        # 첫 번째 페이지 조회 (totalCount 확인용)
        first_query = HolidayQuery(
            solYear=query.solYear,
            solMonth=query.solMonth,
            numOfRows=query.numOfRows or 100,  # 기본값 100으로 설정하여 페이지 수 최소화
            pageNo=1
        )
        first_response = await self._fetch_24divisions_page(first_query)
        all_items = first_response.to_domain_items()

        total_count = first_response.body.totalCount or 0
        num_of_rows = first_query.numOfRows or 100

        # totalCount가 numOfRows보다 크면 추가 페이지 조회
        if total_count > num_of_rows:
            total_pages = (total_count + num_of_rows - 1) // num_of_rows  # 올림 계산

            logger.info(
                f"Fetching all pages for 24 divisions: "
                f"totalCount={total_count}, numOfRows={num_of_rows}, totalPages={total_pages}"
            )

            # 나머지 페이지들 조회
            for page_no in range(2, total_pages + 1):
                page_query = HolidayQuery(
                    solYear=query.solYear,
                    solMonth=query.solMonth,
                    numOfRows=num_of_rows,
                    pageNo=page_no
                )
                page_response = await self._fetch_24divisions_page(page_query)
                all_items.extend(page_response.to_domain_items())
                logger.debug(f"Fetched page {page_no}/{total_pages} for 24 divisions")

        logger.info(f"Fetched total {len(all_items)} 24 divisions from all pages")
        return all_items
