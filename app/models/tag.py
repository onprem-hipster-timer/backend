"""
태그 시스템 모델

- TagGroup: 태그 그룹 (태그를 그룹화)
- Tag: 개별 태그 (그룹에 속함)
- ScheduleTag: Schedule ↔ Tag 다대다 관계 중간 테이블
- ScheduleExceptionTag: ScheduleException ↔ Tag 다대다 관계 중간 테이블
- TimerTag: TimerSession ↔ Tag 다대다 관계 중간 테이블

Note: SQLModel에서 link_model을 사용할 때 순환 참조 문제를 피하기 위해
중간 테이블을 먼저 정의하고, Relationship에서 link_model 클래스를 직접 참조합니다.
"""
from typing import Optional, List, Dict
from uuid import UUID

from sqlalchemy import Column, ForeignKey, UniqueConstraint, JSON
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


class TimerTag(SQLModel, table=True):
    """TimerSession ↔ Tag 다대다 중간 테이블"""
    __tablename__ = "timer_tag"
    __table_args__ = (
        UniqueConstraint('timer_id', 'tag_id', name='uq_timer_tag'),
    )

    timer_id: UUID = Field(
        sa_column=Column(
            ForeignKey("timersession.id", ondelete="CASCADE"),
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


class TodoTag(SQLModel, table=True):
    """Todo ↔ Tag 다대다 중간 테이블"""
    __tablename__ = "todo_tag"
    __table_args__ = (
        UniqueConstraint('todo_id', 'tag_id', name='uq_todo_tag'),
    )

    todo_id: UUID = Field(
        sa_column=Column(
            ForeignKey("todo.id", ondelete="CASCADE"),
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

    # 소유자 (OIDC sub claim)
    owner_id: str = Field(index=True)
    
    name: str = Field(index=True)  # 그룹 이름 (필수)
    color: str  # 색상 (필수, 예: "#FF5733")
    description: Optional[str] = None  # 설명 (선택)

    # Todo 관련 필드
    goal_ratios: Optional[Dict[str, float]] = Field(
        default=None,
        sa_column=Column(JSON, nullable=True)
    )  # 태그별 목표 비율 (예: {"tag_id": 0.3})
    is_todo_group: bool = Field(default=False)  # Todo 그룹 여부

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

    # 소유자 (OIDC sub claim)
    owner_id: str = Field(index=True)
    
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
