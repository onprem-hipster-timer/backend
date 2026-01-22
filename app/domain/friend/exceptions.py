"""
Friend Domain Exceptions

친구 관련 도메인 예외
"""
from app.core.error_handlers import DomainException


class FriendshipNotFoundError(DomainException):
    """친구 관계를 찾을 수 없음"""
    status_code = 404
    detail = "Friendship not found"


class FriendRequestAlreadyExistsError(DomainException):
    """이미 친구 요청이 존재함"""
    status_code = 409
    detail = "Friend request already exists"


class AlreadyFriendsError(DomainException):
    """이미 친구 관계임"""
    status_code = 409
    detail = "Already friends with this user"


class CannotFriendSelfError(DomainException):
    """자기 자신에게 친구 요청 불가"""
    status_code = 400
    detail = "Cannot send friend request to yourself"


class FriendRequestNotPendingError(DomainException):
    """대기 중인 친구 요청이 아님"""
    status_code = 400
    detail = "Friend request is not pending"


class NotFriendRequestRecipientError(DomainException):
    """친구 요청의 수신자가 아님"""
    status_code = 403
    detail = "You are not the recipient of this friend request"


class UserBlockedError(DomainException):
    """차단된 사용자"""
    status_code = 403
    detail = "This user is blocked or has blocked you"


class NotFriendsError(DomainException):
    """친구 관계가 아님"""
    status_code = 403
    detail = "You are not friends with this user"
