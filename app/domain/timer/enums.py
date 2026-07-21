"""
Timer Enums
"""
from enum import Enum


class TimerStatus(str, Enum):
    """타이머 상태"""
    NOT_STARTED = "NOT_STARTED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
