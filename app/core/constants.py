# 상수 정의
from enum import Enum

# 하위호환 재수출 — 정식 정의 위치: app/domain/timer/enums.py
from app.domain.timer.enums import TimerStatus  # noqa: F401


class TagIncludeMode(str, Enum):
    """타이머 태그 포함 모드"""
    NONE = "none"  # 태그 포함 안 함
    TIMER_ONLY = "timer_only"  # 타이머의 태그만 포함
    INHERIT_FROM_SCHEDULE = "inherit_from_schedule"  # 스케줄의 태그를 상속 (타이머 태그 + 스케줄 태그)


class ResourceScope(str, Enum):
    """리소스 조회 범위 (공유 리소스 포함 여부)"""
    MINE = "mine"  # 내 리소스만 (기본값)
    SHARED = "shared"  # 공유된 타인 리소스만
    ALL = "all"  # 내 리소스 + 공유 리소스
