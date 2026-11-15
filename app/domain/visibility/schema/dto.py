"""
Visibility Domain DTO (Data Transfer Objects)

접근권한 관련 데이터 전송 객체
"""
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import ConfigDict, field_validator

from app.core.base_model import CustomModel
from app.models.visibility import VisibilityLevel, ResourceType


class VisibilityUpdate(CustomModel):
    """접근권한 설정 업데이트 DTO"""
    level: VisibilityLevel
    allowed_user_ids: Optional[List[str]] = None  # SELECTED_FRIENDS 레벨에서만 사용
    allowed_emails: Optional[List[str]] = None  # ALLOWED_EMAILS 레벨에서만 사용
    allowed_domains: Optional[List[str]] = None  # ALLOWED_EMAILS 레벨에서만 사용

    @field_validator("allowed_emails", "allowed_domains")
    @classmethod
    def _normalize_email_entries(cls, values: Optional[List[str]]) -> Optional[List[str]]:
        """이메일·도메인은 대소문자를 구분하지 않으므로 앞뒤 공백을 지우고 소문자로 바꾼 뒤 중복을 없앤다."""
        if values is None:
            return None
        return list(dict.fromkeys(value.strip().lower() for value in values))


class VisibilityRead(CustomModel):
    """접근권한 설정 조회 DTO"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    resource_type: ResourceType
    resource_id: UUID
    owner_id: str
    level: VisibilityLevel
    allowed_user_ids: List[str] = []  # AllowList에서 조회
    allowed_emails: List[str] = []  # 이메일 허용 목록에서 조회
    allowed_domains: List[str] = []  # 도메인 허용 목록에서 조회
    created_at: datetime
    updated_at: datetime


class ResourceWithVisibility(CustomModel):
    """접근권한이 포함된 리소스 정보"""
    resource_id: UUID
    resource_type: ResourceType
    owner_id: str
    visibility_level: VisibilityLevel = VisibilityLevel.PRIVATE
    is_shared_with_me: bool = False  # 다른 사용자에게 공유된 것인지
