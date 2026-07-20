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
    """
    마감 취소·Todo 삭제 시 연결 투영 Schedule 처리 정책 (#61)

    서버 디폴트 없음 — 클라이언트가 항상 명시합니다.
    (K8s propagationPolicy 방식: bool이 아닌 enum으로 확장 여지 확보)
    """
    DELETE = "delete"  # 투영 삭제 + visibility cleanup
    UNLINK = "unlink"  # 연결만 해제 — 일반 일정으로 생존 (데이터 보존)
