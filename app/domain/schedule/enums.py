"""
Schedule State Enum
"""
from enum import Enum


class ScheduleState(str, Enum):
    """Schedule 상태"""
    PLANNED = "PLANNED"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
