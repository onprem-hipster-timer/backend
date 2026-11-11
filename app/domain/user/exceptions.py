"""
User Domain Exceptions
"""
from app.core.error_handlers import DomainException


class ConsentVersionMismatchError(DomainException):
    """현재 시행 중인 약관 버전이 아닌 버전에 동의함"""
    status_code = 409
    detail = "Consent version is not current"


class AccountDeletionPendingError(DomainException):
    """탈퇴를 신청한 휴면 계정의 요청"""
    status_code = 403
    detail = "account_deletion_pending"


class AccountDeletedError(DomainException):
    """파기한 계정의 토큰"""
    status_code = 401
    detail = "account_deleted"
