"""
Todo Domain Events (#55)

Todo 변경 사실을 알리는 불변 이벤트. payload는 식별자와 도메인 사실만
담습니다 (doc §4.1) — 수신 핸들러가 같은 트랜잭션에서 현재 상태를
조회해 소유 필드만 투영합니다 (필드 소유권 표: doc §5.1).
"""
from dataclasses import dataclass
from typing import Tuple
from uuid import UUID

from app.domain.todo.enums import LinkedSchedulePolicy
from app.shared.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class TodoEvent(DomainEvent):
    """Todo 이벤트 공통 베이스 — event_key에 todo_id 포함"""
    todo_id: UUID

    def event_key(self) -> tuple:
        return (type(self).__qualname__, str(self.todo_id))


@dataclass(frozen=True, kw_only=True)
class TodoDeadlineSet(TodoEvent):
    """deadline이 새로 설정됨 (생성 시 포함) → 투영 Schedule 생성"""


@dataclass(frozen=True, kw_only=True)
class TodoDeadlineChanged(TodoEvent):
    """deadline 값이 변경됨 → 투영 Schedule 시간 이동"""


@dataclass(frozen=True, kw_only=True)
class TodoDeadlineRemoved(TodoEvent):
    """
    deadline이 제거됨 → 투영 Schedule 정리

    :param policy: 클라이언트가 명시한 투영 처리 정책 (#61 — 디폴트 없음)
    """
    policy: LinkedSchedulePolicy


@dataclass(frozen=True, kw_only=True)
class TodoContentChanged(TodoEvent):
    """제목·설명이 변경됨 → 투영 Schedule에 최신 내용 반영 (Todo 소유 필드)"""


@dataclass(frozen=True, kw_only=True)
class TodoTagsChanged(TodoEvent):
    """태그가 변경됨 → 투영 Schedule 태그 full-replace (D2 계약)"""


@dataclass(frozen=True, kw_only=True)
class TodoDeleted(TodoEvent):
    """
    Todo가 삭제됨 → 연결 Schedule 정리

    :param linked_schedule_ids: 삭제 직전 스냅샷한 연결 Schedule ID.
        `Schedule.source_todo_id`가 `ondelete=SET NULL`이라 삭제 flush
        후에는 조회할 수 없어 이벤트가 사실로서 운반합니다.
    :param policy: 클라이언트가 명시한 투영 처리 정책 (#61 — 디폴트 없음)
    """
    linked_schedule_ids: Tuple[UUID, ...]
    policy: LinkedSchedulePolicy
