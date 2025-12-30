"""
Timer Domain DTO (Data Transfer Objects)

아키텍처 원칙:
- Domain이 자신의 DTO를 정의
- REST API와 GraphQL 모두에서 사용
- Pydantic을 사용한 데이터 검증
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import field_validator

from app.core.base_model import CustomModel
from app.domain.schedule.schema.dto import ScheduleRead


class TimerCreate(CustomModel):
    """타이머 생성 DTO"""
    schedule_id: UUID
    title: Optional[str] = None
    description: Optional[str] = None
    allocated_duration: int  # 할당 시간 (초 단위)

    @field_validator("allocated_duration")
    @classmethod
    def validate_allocated_duration(cls, v):
        """allocated_duration 검증"""
        if v <= 0:
            raise ValueError("allocated_duration must be positive")
        return v


class TimerRead(CustomModel):
    """타이머 조회 DTO"""
    id: UUID
    schedule_id: UUID
    title: Optional[str] = None
    description: Optional[str] = None
    allocated_duration: int
    elapsed_time: int
    status: str  # TimerStatus enum 값
    started_at: Optional[datetime] = None
    paused_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    # 일정 정보 포함
    schedule: ScheduleRead


class TimerUpdate(CustomModel):
    """타이머 업데이트 DTO"""
    title: Optional[str] = None
    description: Optional[str] = None
