from datetime import datetime
from typing import Optional, TYPE_CHECKING, List, Any
from uuid import UUID

from sqlalchemy import Column, ForeignKey, JSON
from sqlmodel import Field, Relationship

from app.models.base import UUIDBase, TimestampMixin
from app.models.tag import TimerTag

if TYPE_CHECKING:
    from app.models.schedule import Schedule
    from app.models.tag import Tag
    from app.models.todo import Todo


class TimerSession(UUIDBase, TimestampMixin, table=True):
    """타이머 세션 모델"""
    # 소유자 (OIDC sub claim)
    owner_id: str = Field(index=True)

    # Schedule 연결 (Optional - 독립 타이머 또는 Todo 전용 타이머 가능)
    schedule_id: Optional[UUID] = Field(
        default=None,
        sa_column=Column(
            ForeignKey("schedule.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )

    # Todo 연결 (Optional - Schedule 또는 독립 타이머 가능)
    todo_id: Optional[UUID] = Field(
        default=None,
        sa_column=Column(
            ForeignKey("todo.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )

    # 타이머 기본 정보
    title: Optional[str] = None
    description: Optional[str] = None

    # 시간 관련 필드
    allocated_duration: int  # 할당 시간 (초 단위)
    elapsed_time: int = 0  # 경과 시간 (초 단위)

    # 상태 및 시간 추적
    status: str  # TimerStatus enum 값 (문자열로 저장)
    started_at: Optional[datetime] = None
    paused_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None

    # 일시정지/재개 이력 (WebSocket 기반 멀티 플랫폼 동기화용)
    # 예시: [
    #   {"action": "start", "at": "2026-01-28T10:00:00Z"},
    #   {"action": "pause", "at": "2026-01-28T10:30:00Z", "elapsed": 1800},
    #   {"action": "resume", "at": "2026-01-28T10:35:00Z"},
    #   {"action": "stop", "at": "2026-01-28T11:00:00Z", "elapsed": 3300}
    # ]
    pause_history: List[dict[str, Any]] = Field(
        default=[],
        sa_column=Column(JSON, nullable=False, default=list)
    )

    # Relationships
    schedule: Optional["Schedule"] = Relationship(back_populates="timers")
    todo: Optional["Todo"] = Relationship(back_populates="timers")

    # 태그 관계 (다대다)
    tags: List["Tag"] = Relationship(
        link_model=TimerTag,
        sa_relationship_kwargs={"lazy": "selectin"}  # N+1 방지
    )
