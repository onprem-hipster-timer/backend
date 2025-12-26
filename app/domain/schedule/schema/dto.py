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
from sqlmodel import SQLModel

from app.utils.validators import validate_time_order


class ScheduleCreate(SQLModel):
    """일정 생성 DTO"""
    title: str
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime

    @field_validator("end_time")
    def validate_time(cls, end_time, info):
        validate_time_order(info.data.get("start_time"), end_time)
        return end_time


class ScheduleRead(ScheduleCreate):
    """일정 조회 DTO"""
    id: UUID
    created_at: datetime


class ScheduleUpdate(SQLModel):
    """일정 업데이트 DTO"""
    title: Optional[str] = None
    description: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    @field_validator("end_time")
    def validate_time(cls, end_time, info):
        validate_time_order(info.data.get("start_time"), end_time)
        return end_time

