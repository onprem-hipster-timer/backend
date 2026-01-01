"""
Holiday API Client

외부 API 호출 전담 클래스
한국천문연구원 특일 정보제공 서비스(OpenAPI)와의 통신 담당

객체지향 원칙 준수:
- Single Responsibility: 각 메서드는 하나의 책임만 담당
- 메서드 분리로 재사용성 및 테스트 용이성 향상
"""
import logging
from typing import Dict, Any

import httpx

from app.core.config import settings
from app.domain.holiday.exceptions import (
    HolidayApiError,
    HolidayApiKeyError,
    HolidayApiResponseError,
)
from app.domain.holiday.schema.dto import HolidayQuery, HolidayApiResponse

logger = logging.getLogger(__name__)


class HolidayApiClient:
    """
    국경일 정보 API 클라이언트
    
    외부 API 호출 및 응답 파싱 전담
    """
    
    BASE_URL = settings.HOLIDAY_API_BASE_URL
    ENDPOINT = "/getHoliDeInfo"
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

        return params
    
    def _build_url(self) -> str:
        """
        API 요청 URL 구성
        
        :return: 완전한 API URL
        """
        return f"{self.BASE_URL}{self.ENDPOINT}"
    
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
    
    async def fetch_holidays(self, query: HolidayQuery) -> HolidayApiResponse:
        """
        API에서 국경일 정보 조회
        
        객체지향 원칙 준수:
        - 각 단계를 별도 메서드로 분리
        - 단일 책임 원칙 준수
        - 메서드 체이닝으로 가독성 향상
        
        :param query: 조회 요청 데이터 (solYear, solMonth, numOfRows)
        :return: API 응답 객체
        :raises HolidayApiError: API 호출 실패
        :raises HolidayApiResponseError: API 응답 오류
        """
        return self._validate_response(
            self._parse_response(
                self._normalize_response_data(
                    await self._make_request(
                        self._build_url(),
                        self._build_params(query)
                    )
                )
            )
        )

