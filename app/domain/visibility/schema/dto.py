"""
Visibility Domain DTO (Data Transfer Objects)

가시성 관련 데이터 전송 객체
"""
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import ConfigDict

from app.core.base_model import CustomModel
from app.models.visibility import VisibilityLevel, ResourceType


class VisibilityUpdate(CustomModel):
    """가시성 설정 업데이트 DTO"""
    level: VisibilityLevel
    allowed_user_ids: Optional[List[str]] = None  # SELECTED_FRIENDS 레벨에서만 사용


class VisibilityRead(CustomModel):
    """가시성 설정 조회 DTO"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    resource_type: ResourceType
    resource_id: UUID
    owner_id: str
    level: VisibilityLevel
    allowed_user_ids: List[str] = []  # AllowList에서 조회
    created_at: datetime
    updated_at: datetime


class ResourceWithVisibility(CustomModel):
    """가시성이 포함된 리소스 정보"""
    resource_id: UUID
    resource_type: ResourceType
    owner_id: str
    visibility_level: VisibilityLevel = VisibilityLevel.PRIVATE
    is_shared_with_me: bool = False  # 다른 사용자에게 공유된 것인지
