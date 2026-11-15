"""
TodoGroup Domain DTO

생성·수정 DTO에는 is_default가 없다. 기본 그룹은 서버만 만든다(사용자당 하나).
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import ConfigDict, field_validator
from pydantic.experimental.missing_sentinel import MISSING

from app.core.base_model import CustomModel
from app.utils.validators import validate_color


class TodoGroupCreate(CustomModel):
    """할 일 그룹 생성 DTO"""
    name: str
    color: str  # 예: "#FF5733"
    description: Optional[str] = None

    @field_validator("color")
    @classmethod
    def validate_color_field(cls, v: str) -> str:
        """색상 코드 검증 (HEX 형식)"""
        return validate_color(v)


class TodoGroupRead(CustomModel):
    """할 일 그룹 조회 DTO"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    color: str
    description: Optional[str] = None
    is_default: bool  # 기본 그룹이면 true. 지울 수 없고, 그룹을 정하지 않은 할 일이 들어간다
    created_at: datetime
    updated_at: datetime


class TodoGroupUpdate(CustomModel):
    """할 일 그룹 업데이트 DTO"""
    name: str | None = MISSING
    color: str | None = MISSING
    description: str | None = MISSING

    @field_validator("color")
    @classmethod
    def validate_color_field(cls, v: str | None) -> str | None:
        """색상 코드 검증 (HEX 형식)"""
        return validate_color(v)
