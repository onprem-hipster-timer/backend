"""
Visibility Domain Exceptions

가시성 관련 도메인 예외
"""
from app.core.error_handlers import DomainException


class AccessDeniedError(DomainException):
    """접근 권한 없음"""
    status_code = 403
    detail = "You don't have permission to access this resource"


class VisibilityNotFoundError(DomainException):
    """가시성 설정을 찾을 수 없음"""
    status_code = 404
    detail = "Visibility setting not found"


class InvalidVisibilityLevelError(DomainException):
    """잘못된 가시성 레벨"""
    status_code = 400
    detail = "Invalid visibility level"


class CannotShareWithNonFriendError(DomainException):
    """친구가 아닌 사용자와 공유 불가"""
    status_code = 400
    detail = "Cannot share with non-friend users in SELECTED_FRIENDS mode"
