"""
User Domain Model

도메인 레벨의 UserProfile 모델
ORM 모델(app/models/user_profile.py)을 참조합니다.
"""
from app.models.user_profile import UserProfile

# Re-export for domain use
__all__ = ["UserProfile"]
