from uuid import UUID
from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel

class ScheduleCreate(SQLModel):
    title: str
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime

class ScheduleRead(ScheduleCreate):
    id: UUID
    created_at: datetime

class ScheduleUpdate(SQLModel):
    title: Optional[UUID] = None
    description: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
