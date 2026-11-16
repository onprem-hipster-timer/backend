"""
User Domain Exceptions
"""
from app.core.error_handlers import DomainException


class AccountDeletionPendingError(DomainException):
    """탈퇴를 신청한 휴면 계정의 요청 (계정이 잠겨 있다)"""
    status_code = 423
    detail = "account_deletion_pending"


class AccountDeletedError(DomainException):
    """파기한 계정의 토큰"""
    status_code = 401
    detail = "account_deleted"
