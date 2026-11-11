"""
User Domain Exceptions
"""
from app.core.error_handlers import DomainException


class ConsentVersionMismatchError(DomainException):
    """현재 시행 중인 약관 버전이 아닌 버전에 동의함"""
    status_code = 409
    detail = "Consent version is not current"


class AccountDeletionPendingError(DomainException):
    """탈퇴를 신청한 휴면 계정의 요청 (계정이 잠겨 있다)"""
    status_code = 423
    detail = "account_deletion_pending"


class AccountDeletedError(DomainException):
    """파기한 계정의 토큰"""
    status_code = 401
    detail = "account_deleted"


class ConsentRequiredError(DomainException):
    """현재 시행 중인 약관 버전에 동의하지 않음 (동의라는 선행 조건이 필요하다)"""
    status_code = 428
    detail = "consent_required"
