"""
Timer Enums
"""
from enum import Enum


class LinkedTimerPolicy(str, Enum):
    """연결된 Todo·Schedule 삭제 시 연결 타이머 처리 정책. 서버 기본값은 없다."""
    DELETE = "delete"  # 타이머 삭제 + visibility cleanup
    UNLINK = "unlink"  # 연결만 해제 — 독립 타이머로 생존 (실행 중이면 계속 실행)
