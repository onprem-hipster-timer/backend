"""
Todo 모델

Todo는 독립적인 엔티티로 Schedule과 분리됩니다.
deadline이 있으면 별도의 Schedule을 생성할 수 있습니다.
"""
from datetime import datetime
from typing import Optional, TYPE_CHECKING, List
from uuid import UUID

from sqlalchemy import Column, ForeignKey, Enum as SQLEnum
from sqlmodel import Field, Relationship

from app.domain.todo.enums import TodoStatus
from app.models.base import UUIDBase, TimestampMixin
from app.models.tag import TodoTag

if TYPE_CHECKING:
    from app.models.schedule import Schedule
    from app.models.tag import Tag, TagGroup


class Todo(UUIDBase, TimestampMixin, table=True):
    """Todo 모델"""
    __tablename__ = "todo"

    # 소유자 (OIDC sub claim)
    owner_id: str = Field(index=True)
    
    title: str
    description: Optional[str] = None
    deadline: Optional[datetime] = None  # 마감기간

    # TagGroup 참조 (필수)
    tag_group_id: UUID = Field(
        sa_column=Column(
            ForeignKey("tag_group.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        )
    )

    # Todo self-reference (트리 구조)
    # 부모 삭제 시 자식은 삭제되지 않고 parent_id가 NULL로 설정됨 (루트로 승격)
    parent_id: Optional[UUID] = Field(
        default=None,
        sa_column=Column(
            ForeignKey("todo.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        )
    )

    # Status enum
    status: TodoStatus = Field(
        default=TodoStatus.UNSCHEDULED,
        sa_column=Column(
            SQLEnum(TodoStatus, native_enum=False, values_callable=lambda x: [e.value for e in x]),
            nullable=False,
            default=TodoStatus.UNSCHEDULED.value,
        )
    )

    # Relationships
    tag_group: "TagGroup" = Relationship()
    parent: Optional["Todo"] = Relationship(
        back_populates="children",
        sa_relationship_kwargs={"remote_side": "Todo.id"}
    )
    # 부모 삭제 시 자식이 함께 삭제되지 않도록 cascade 제거
    children: List["Todo"] = Relationship(
        back_populates="parent",
    )
    schedules: List["Schedule"] = Relationship(
        back_populates="source_todo"
    )
    tags: List["Tag"] = Relationship(
        link_model=TodoTag,
        sa_relationship_kwargs={"lazy": "selectin"}  # N+1 방지
    )
