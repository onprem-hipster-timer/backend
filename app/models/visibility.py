"""
ResourceVisibility 모델

리소스(Schedule, Timer, Todo)의 가시성을 관리합니다.
다형성 패턴을 사용하여 모든 리소스 타입에 동일한 가시성 로직을 적용합니다.
"""
from enum import Enum
from uuid import UUID

from sqlalchemy import Column, Enum as SQLEnum, ForeignKey, UniqueConstraint, Index
from sqlmodel import Field

from app.models.base import UUIDBase, TimestampMixin


class VisibilityLevel(str, Enum):
    """가시성 레벨"""
    PRIVATE = "private"           # 본인만 (기본값)
    FRIENDS = "friends"           # 모든 친구
    SELECTED_FRIENDS = "selected" # 선택한 친구만
    PUBLIC = "public"             # 전체 공개


class ResourceType(str, Enum):
    """리소스 타입"""
    SCHEDULE = "schedule"
    TIMER = "timer"
    TODO = "todo"


class ResourceVisibility(UUIDBase, TimestampMixin, table=True):
    """
    리소스 가시성 설정
    
    - resource_type: 리소스 종류 (schedule, timer, todo)
    - resource_id: 리소스 UUID
    - owner_id: 리소스 소유자 ID
    - level: 가시성 레벨
    
    Note: 레코드가 없으면 PRIVATE으로 간주
    """
    __tablename__ = "resource_visibility"
    
    # 리소스 타입
    resource_type: ResourceType = Field(
        sa_column=Column(
            SQLEnum(ResourceType, native_enum=False, values_callable=lambda x: [e.value for e in x]),
            nullable=False,
        )
    )
    
    # 리소스 ID (외래 키 없음 - 다형성 지원)
    resource_id: UUID = Field(index=True)
    
    # 소유자 ID (OIDC sub claim)
    owner_id: str = Field(index=True)
    
    # 가시성 레벨
    level: VisibilityLevel = Field(
        default=VisibilityLevel.PRIVATE,
        sa_column=Column(
            SQLEnum(VisibilityLevel, native_enum=False, values_callable=lambda x: [e.value for e in x]),
            nullable=False,
            default=VisibilityLevel.PRIVATE.value,
        )
    )
    
    __table_args__ = (
        # 리소스별 하나의 가시성 설정만 허용
        UniqueConstraint("resource_type", "resource_id", name="uq_resource_visibility"),
        # 쿼리 최적화
        Index("ix_visibility_resource", "resource_type", "resource_id"),
        Index("ix_visibility_owner_type", "owner_id", "resource_type"),
    )


class VisibilityAllowList(UUIDBase, table=True):
    """
    가시성 허용 목록 (SELECTED_FRIENDS 레벨용)
    
    특정 리소스에 대해 접근을 허용할 사용자 목록
    """
    __tablename__ = "visibility_allow_list"
    
    # 가시성 설정 참조
    visibility_id: UUID = Field(
        sa_column=Column(
            ForeignKey("resource_visibility.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    
    # 허용된 사용자 ID (OIDC sub claim)
    allowed_user_id: str = Field(index=True)
    
    __table_args__ = (
        # 동일한 visibility에 대해 사용자 중복 방지
        UniqueConstraint("visibility_id", "allowed_user_id", name="uq_allow_list_entry"),
    )
