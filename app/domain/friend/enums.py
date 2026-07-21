"""
Friend Enums
"""
from enum import Enum


class FriendshipStatus(str, Enum):
    """친구 관계 상태"""
    PENDING = "pending"  # 요청 대기 중
    ACCEPTED = "accepted"  # 수락됨 (친구)
    BLOCKED = "blocked"  # 차단됨
