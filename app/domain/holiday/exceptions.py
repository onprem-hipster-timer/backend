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
