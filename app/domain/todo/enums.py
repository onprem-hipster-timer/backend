"""
Todo Status Enum
"""
from enum import Enum


class TodoStatus(str, Enum):
    """Todo 상태"""
    UNSCHEDULED = "UNSCHEDULED"
    SCHEDULED = "SCHEDULED"
    DONE = "DONE"
    CANCELLED = "CANCELLED"
