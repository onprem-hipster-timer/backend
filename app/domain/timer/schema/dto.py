"""
Timer Domain DTO (Data Transfer Objects)

아키텍처 원칙:
- Domain이 자신의 DTO를 정의
- REST API와 GraphQL 모두에서 사용
- Pydantic을 사용한 데이터 검증
"""
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from pydantic import field_validator

from app.core.base_model import CustomModel
from app.domain.dateutil.service import convert_utc_naive_to_timezone
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

    def to_timezone(self, tz: timezone | str | None) -> "TimerRead":
        """
        UTC naive datetime 필드를 지정된 타임존의 aware datetime으로 변환
        
        :param tz: 타임존 (timezone 객체, 문자열, 또는 None)
        :return: 타임존이 변환된 새로운 TimerRead 인스턴스
        """
        if tz is None:
            return self
        
        data = self.model_dump()
        
        # Timer의 datetime 필드 변환
        timer_datetime_fields = ["started_at", "paused_at", "ended_at", "created_at", "updated_at"]
        for field in timer_datetime_fields:
            if data.get(field) is not None:
                dt = data[field]
                if isinstance(dt, datetime):
                    data[field] = convert_utc_naive_to_timezone(dt, tz)
        
        # Schedule도 타임존 변환 (model_dump()로 dict가 되었으므로 ScheduleRead로 변환)
        if data.get("schedule"):
            schedule_read = ScheduleRead(**data["schedule"])
            data["schedule"] = schedule_read.to_timezone(tz)
        
        return TimerRead(**data)


class TimerUpdate(CustomModel):
    """타이머 업데이트 DTO"""
    title: Optional[str] = None
    description: Optional[str] = None
