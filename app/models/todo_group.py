"""
할 일 그룹 모델

할 일은 반드시 하나의 할 일 그룹에 속한다. 사용자마다 기본 그룹(is_default) 하나를 서버가 보장한다.
태그를 묶는 태그 그룹(app/models/tag.py의 TagGroup)과는 별개다.
"""
from typing import Optional

from sqlalchemy import Boolean, Column, Index, false, text
from sqlmodel import Field

from app.models.base import UUIDBase, TimestampMixin


class TodoGroup(UUIDBase, TimestampMixin, table=True):
    """할 일 그룹"""
    __tablename__ = "todo_group"
    __table_args__ = (
        # 사용자당 기본 그룹은 하나 — 동시에 만들려 해도 DB가 최종 보장
        Index(
            "uq_todo_group_owner_default",
            "owner_id",
            unique=True,
            postgresql_where=text("is_default"),
            sqlite_where=text("is_default"),
        ),
    )

    # 소유자 (OIDC sub claim)
    owner_id: str = Field(index=True)

    name: str
    color: str  # 예: "#FF5733"
    description: Optional[str] = None

    # 기본 그룹. 서버가 만들고 지울 수 없다. API로는 바꿀 수 없다
    is_default: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=false()),
    )
