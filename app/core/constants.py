# 상수 정의
from enum import Enum

# 일정 상태 (필요시 확장)
SCHEDULE_STATUS_PENDING = "pending"
SCHEDULE_STATUS_CONFIRMED = "confirmed"
SCHEDULE_STATUS_CANCELLED = "cancelled"


class TimerStatus(str, Enum):
    """타이머 상태"""
    NOT_STARTED = "not_started"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
