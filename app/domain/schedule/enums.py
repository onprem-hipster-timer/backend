"""
Schedule State Enum
"""
from enum import Enum


class ScheduleState(str, Enum):
    """Schedule 상태"""
    PLANNED = "PLANNED"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class SourceTodoPolicy(str, Enum):
    """
    투영 일정이 마감 표시이기를 그만둘 때(삭제·반복 전환) source Todo 처리 정책.
    서버 기본값은 없다.
    """
    CLEAR_DEADLINE = "clear_deadline"  # Todo의 deadline도 제거
    KEEP_DEADLINE = "keep_deadline"    # deadline 유지 (연동 플래그만 해제)
