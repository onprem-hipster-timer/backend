from datetime import datetime
from typing import Optional, TYPE_CHECKING, List
from uuid import UUID

from sqlalchemy import Column, ForeignKey
from sqlmodel import Field, Relationship

from app.models.base import UUIDBase, TimestampMixin
from app.models.tag import TimerTag

if TYPE_CHECKING:
    from app.models.schedule import Schedule
    from app.models.tag import Tag


class TimerSession(UUIDBase, TimestampMixin, table=True):
    """타이머 세션 모델"""
    schedule_id: UUID = Field(
        sa_column=Column(
            ForeignKey("schedule.id", ondelete="CASCADE"),
            nullable=False,
            index=True,  # Column 내부에 index 설정
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

    # Relationship
    schedule: "Schedule" = Relationship(back_populates="timers")
    
    # 태그 관계 (다대다)
    tags: List["Tag"] = Relationship(
        link_model=TimerTag,
        sa_relationship_kwargs={"lazy": "selectin"}  # N+1 방지
    )
