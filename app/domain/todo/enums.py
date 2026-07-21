"""
Todo Enums
"""
from enum import Enum


class TodoStatus(str, Enum):
    """Todo 상태"""
    UNSCHEDULED = "UNSCHEDULED"
    SCHEDULED = "SCHEDULED"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


class LinkedSchedulePolicy(str, Enum):
    """마감 취소·Todo 삭제 시 연결 Schedule의 수명주기 처리 정책. 서버 기본값은 없다."""
    DELETE = "delete"  # 투영 삭제 + visibility cleanup
    UNLINK = "unlink"  # 연결만 해제 — 일반 일정으로 생존 (데이터 보존)
