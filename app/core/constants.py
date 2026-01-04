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


class TagIncludeMode(str, Enum):
    """타이머 태그 포함 모드"""
    NONE = "none"  # 태그 포함 안 함
    TIMER_ONLY = "timer_only"  # 타이머의 태그만 포함
    INHERIT_FROM_SCHEDULE = "inherit_from_schedule"  # 스케줄의 태그를 상속 (타이머 태그 + 스케줄 태그)
