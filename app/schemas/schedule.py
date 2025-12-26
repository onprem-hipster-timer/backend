from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import field_validator
from sqlmodel import SQLModel

from app.utils.validators import validate_time_order


class ScheduleCreate(SQLModel):
    title: str
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime

    @field_validator("end_time")
    def validate_time(cls, end_time, info):
        validate_time_order(info.data.get("start_time"), end_time)
        return end_time


class ScheduleRead(ScheduleCreate):
    id: UUID
    created_at: datetime

class ScheduleUpdate(SQLModel):
    title: Optional[str] = None
    description: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    @field_validator("end_time")
    def validate_time(cls, end_time, info):
        validate_time_order(info.data.get("start_time"), end_time)
        return end_time
