"""
User Domain Exceptions
"""
from app.core.error_handlers import DomainException


class ConsentVersionMismatchError(DomainException):
    """현재 시행 중인 약관 버전이 아닌 버전에 동의함"""
    status_code = 409
    detail = "Consent version is not current"
