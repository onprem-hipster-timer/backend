"""
Visibility Domain Enums

접근권한 관련 열거형 — 자료형 enum의 정식 정의 위치.
저장 컬럼은 app/models/visibility.py가 str_enum_column으로 매핑한다.
"""
from enum import Enum


class VisibilityLevel(str, Enum):
    """접근권한 레벨"""
    PRIVATE = "private"  # 본인만 (기본값)
    FRIENDS = "friends"  # 모든 친구
    SELECTED_FRIENDS = "selected"  # 선택한 친구만
    ALLOWED_EMAILS = "allowed_emails"  # 허용된 이메일/도메인만
    PUBLIC = "public"  # 전체 공개


class ResourceType(str, Enum):
    """리소스 타입"""
    SCHEDULE = "schedule"
    TIMER = "timer"
    TODO = "todo"
    MEETING = "meeting"
