"""
Meeting Domain Enums

일정 조율 관련 열거형
"""
from enum import IntEnum


class DayOfWeek(IntEnum):
    """요일 (ISO 8601 기준: 월요일=0)"""
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6
