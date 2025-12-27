from datetime import datetime
from typing import Optional
from uuid import UUID

from app.models.base import UUIDBase, TimestampMixin


class Schedule(UUIDBase, TimestampMixin, table=True):
    title: str
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime
    
    # 반복 일정 필드
    recurrence_rule: Optional[str] = None  # RRULE 형식: "FREQ=WEEKLY;BYDAY=MO"
    recurrence_end: Optional[datetime] = None  # 반복 종료일
    parent_id: Optional[UUID] = None  # 원본 일정 ID (예외 인스턴스용)


class ScheduleException(UUIDBase, TimestampMixin, table=True):
    """반복 일정의 예외 인스턴스 (특정 날짜만 수정/삭제)"""
    parent_id: UUID  # 원본 일정 ID
    exception_date: datetime  # 예외가 발생한 날짜
    is_deleted: bool = False  # 삭제된 인스턴스인지
    # 수정된 경우: 새로운 일정 데이터
    title: Optional[str] = None
    description: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
