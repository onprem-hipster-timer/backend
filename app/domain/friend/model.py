"""
Friend Domain Model

도메인 레벨의 Friendship 모델
ORM 모델(app/models/friendship.py)을 래핑하거나 참조합니다.
"""
from app.models.friendship import Friendship, FriendshipStatus

# Re-export for domain use
__all__ = ["Friendship", "FriendshipStatus"]
