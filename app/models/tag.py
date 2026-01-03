"""
태그 시스템 모델

- TagGroup: 태그 그룹 (태그를 그룹화)
- Tag: 개별 태그 (그룹에 속함)
- ScheduleTag: Schedule ↔ Tag 다대다 관계 중간 테이블
- ScheduleExceptionTag: ScheduleException ↔ Tag 다대다 관계 중간 테이블

Note: SQLModel에서 link_model을 사용할 때 순환 참조 문제를 피하기 위해
중간 테이블을 먼저 정의하고, Relationship에서 link_model 클래스를 직접 참조합니다.
"""
from typing import Optional, List
from uuid import UUID

from sqlalchemy import Column, ForeignKey, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from app.models.base import UUIDBase, TimestampMixin


# ============================================================
# 중간 테이블 (먼저 정의 - 순환 참조 방지)
# ============================================================

class ScheduleTag(SQLModel, table=True):
    """Schedule ↔ Tag 다대다 중간 테이블"""
    __tablename__ = "schedule_tag"
    __table_args__ = (
        UniqueConstraint('schedule_id', 'tag_id', name='uq_schedule_tag'),
    )
    
    schedule_id: UUID = Field(
        sa_column=Column(
            ForeignKey("schedule.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=True,
        )
    )
    tag_id: UUID = Field(
        sa_column=Column(
            ForeignKey("tag.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=True,
        )
    )


class ScheduleExceptionTag(SQLModel, table=True):
    """ScheduleException ↔ Tag 다대다 중간 테이블"""
    __tablename__ = "schedule_exception_tag"
    __table_args__ = (
        UniqueConstraint('schedule_exception_id', 'tag_id', name='uq_schedule_exception_tag'),
    )
    
    schedule_exception_id: UUID = Field(
        sa_column=Column(
            ForeignKey("scheduleexception.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=True,
        )
    )
    tag_id: UUID = Field(
        sa_column=Column(
            ForeignKey("tag.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=True,
        )
    )


# ============================================================
# 메인 모델
# ============================================================

class TagGroup(UUIDBase, TimestampMixin, table=True):
    """태그 그룹"""
    __tablename__ = "tag_group"
    
    name: str = Field(index=True)  # 그룹 이름 (필수)
    color: str  # 색상 (필수, 예: "#FF5733")
    description: Optional[str] = None  # 설명 (선택)
    
    # Relationship (일대다)
    tags: List["Tag"] = Relationship(
        back_populates="group",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )


class Tag(UUIDBase, TimestampMixin, table=True):
    """태그"""
    __tablename__ = "tag"
    __table_args__ = (
        # 그룹 내 태그 이름 고유성 제약
        UniqueConstraint('group_id', 'name', name='uq_tag_group_name'),
    )
    
    name: str = Field(index=True)  # 태그 이름 (필수)
    color: str  # 색상 (필수, 예: "#FF5733")
    description: Optional[str] = None  # 설명 (선택)
    
    # 그룹 참조 (다대일)
    group_id: UUID = Field(
        sa_column=Column(
            ForeignKey("tag_group.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    
    # Relationship
    group: "TagGroup" = Relationship(back_populates="tags")

