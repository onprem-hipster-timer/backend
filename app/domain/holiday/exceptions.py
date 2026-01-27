"""
Holiday Domain Exceptions

아키텍처 원칙:
- Domain Exception은 status_code를 포함
- Exception Handler에서 HTTP로 자동 변환
"""
from app.core.error_handlers import DomainException


class HolidayApiError(DomainException):
    """국경일 API 호출 오류"""
    status_code = 502
    detail = "Failed to fetch holiday information from external API"


class HolidayApiKeyError(DomainException):
    """국경일 API 키 오류"""
    status_code = 500
    detail = "Holiday API service key is not configured"


class HolidayApiResponseError(DomainException):
    """국경일 API 응답 오류"""
    status_code = 502
    detail = "Invalid response from holiday API"


class HolidayDataNotAvailable(DomainException):
    """요청한 연도의 공휴일 데이터가 아직 준비되지 않음"""
    status_code = 422
    detail = "해당 연도의 공휴일 데이터가 아직 준비되지 않았습니다"
