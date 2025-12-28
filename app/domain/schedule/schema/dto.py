"""
Schedule Domain DTO (Data Transfer Objects)

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
from app.utils.datetime_utils import ensure_utc_naive
from app.utils.validators import validate_time_order


class ScheduleCreate(CustomModel):
    """일정 생성 DTO"""
    title: str
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime
    recurrence_rule: Optional[str] = None  # RRULE 형식: "FREQ=WEEKLY;BYDAY=MO"
    recurrence_end: Optional[datetime] = None  # 반복 종료일

    @field_validator("start_time", "end_time", "recurrence_end")
    @classmethod
    def ensure_utc_naive_datetime(cls, v):
        """datetime 필드를 UTC naive로 변환"""
        return ensure_utc_naive(v) if v is not None else None

    @field_validator("end_time")
    def validate_time(cls, end_time, info):
        validate_time_order(info.data.get("start_time"), end_time)
        return end_time


class ScheduleRead(ScheduleCreate):
    """일정 조회 DTO"""
    id: UUID
    created_at: datetime


class ScheduleUpdate(CustomModel):
    """일정 업데이트 DTO"""
    title: Optional[str] = None
    description: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    recurrence_rule: Optional[str] = None  # RRULE 형식: "FREQ=WEEKLY;BYDAY=MO"
    recurrence_end: Optional[datetime] = None  # 반복 종료일

    @field_validator("start_time", "end_time", "recurrence_end")
    @classmethod
    def ensure_utc_naive_datetime(cls, v):
        """datetime 필드를 UTC naive로 변환"""
        return ensure_utc_naive(v) if v is not None else None

    @field_validator("end_time")
    def validate_time(cls, end_time, info):
        validate_time_order(info.data.get("start_time"), end_time)
        return end_time
