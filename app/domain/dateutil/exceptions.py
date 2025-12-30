"""
Dateutil Domain Exceptions

아키텍처 원칙:
- Domain Exception은 status_code를 포함
- Exception Handler에서 HTTP로 자동 변환
"""
from app.core.error_handlers import DomainException


class InvalidTimezoneError(DomainException):
    """잘못된 타임존 형식"""
    status_code = 400
    detail = "Invalid timezone format"
