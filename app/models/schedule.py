from typing import Optional
from datetime import datetime
from app.models.base import UUIDBase, TimestampMixin

class Schedule(UUIDBase, TimestampMixin, table=True):
    title: str
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime