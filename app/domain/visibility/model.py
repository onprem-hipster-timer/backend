"""
Visibility Domain Model

도메인 레벨의 Visibility 모델
ORM 모델(app/models/visibility.py)을 래핑하거나 참조합니다.
"""
from app.domain.visibility.enums import ResourceType, VisibilityLevel
from app.models.visibility import (
    ResourceVisibility,
    VisibilityAllowList,
)

# Re-export for domain use
__all__ = [
    "ResourceVisibility",
    "VisibilityAllowList",
    "VisibilityLevel",
    "ResourceType",
]
