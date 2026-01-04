"""
Tag Domain DTO (Data Transfer Objects)

아키텍처 원칙:
- Domain이 자신의 DTO를 정의
- REST API와 GraphQL 모두에서 사용
- Pydantic을 사용한 데이터 검증
"""
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import ConfigDict, field_validator

from app.core.base_model import CustomModel
from app.utils.validators import validate_color


# ============================================================
# TagGroup DTO
# ============================================================

class TagGroupCreate(CustomModel):
    """태그 그룹 생성 DTO"""
    name: str
    color: str  # 예: "#FF5733"
    description: Optional[str] = None

    @field_validator("color")
    @classmethod
    def validate_color_field(cls, v: str) -> str:
        """색상 코드 검증 (HEX 형식)"""
        return validate_color(v)


class TagGroupRead(CustomModel):
    """태그 그룹 조회 DTO"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    color: str
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class TagGroupReadWithTags(TagGroupRead):
    """태그 그룹 조회 DTO (태그 포함)"""
    tags: List["TagRead"] = []


class TagGroupUpdate(CustomModel):
    """태그 그룹 업데이트 DTO"""
    name: Optional[str] = None
    color: Optional[str] = None
    description: Optional[str] = None

    @field_validator("color")
    @classmethod
    def validate_color_field(cls, v: Optional[str]) -> Optional[str]:
        """색상 코드 검증 (HEX 형식)"""
        return validate_color(v)


# ============================================================
# Tag DTO
# ============================================================

class TagCreate(CustomModel):
    """태그 생성 DTO"""
    name: str
    color: str  # 예: "#FF5733"
    description: Optional[str] = None
    group_id: UUID

    @field_validator("color")
    @classmethod
    def validate_color_field(cls, v: str) -> str:
        """색상 코드 검증 (HEX 형식)"""
        return validate_color(v)


class TagRead(CustomModel):
    """태그 조회 DTO"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    color: str
    description: Optional[str] = None
    group_id: UUID
    created_at: datetime
    updated_at: datetime


class TagReadWithGroup(TagRead):
    """태그 조회 DTO (그룹 정보 포함)"""
    group: TagGroupRead


class TagUpdate(CustomModel):
    """태그 업데이트 DTO"""
    name: Optional[str] = None
    color: Optional[str] = None
    description: Optional[str] = None

    # group_id는 변경 불가 (태그 이동 시 삭제 후 재생성)

    @field_validator("color")
    @classmethod
    def validate_color_field(cls, v: Optional[str]) -> Optional[str]:
        """색상 코드 검증 (HEX 형식)"""
        return validate_color(v)


# Forward reference 해결
TagGroupReadWithTags.model_rebuild()
