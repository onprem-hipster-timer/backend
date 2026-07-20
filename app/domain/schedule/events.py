"""
Schedule Domain Events

역전파(Schedule→Todo)는 `source_todo_id`가 있는 투영 일정에 한정된다.
"""
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from app.shared.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class ScheduleEvent(DomainEvent):
    """Schedule 이벤트 공통 베이스 — event_key에 schedule_id 포함"""
    schedule_id: UUID

    def event_key(self) -> tuple:
        return (type(self).__qualname__, str(self.schedule_id))


@dataclass(frozen=True, kw_only=True)
class ScheduleTimeChanged(ScheduleEvent):
    """일정 시간이 변경됨. origin이 TODO면 재전파하지 않는다."""


@dataclass(frozen=True, kw_only=True)
class ScheduleDeleted(ScheduleEvent):
    """
    일정이 삭제됨

    :param source_todo_id: 삭제 직전 스냅샷 (row가 사라져 사후 조회 불가).
        Todo와 deadline은 유지된다 — 삭제는 캘린더 표시 제거일 뿐.
    """
    source_todo_id: Optional[UUID]


@dataclass(frozen=True, kw_only=True)
class ScheduleCreatedWithTodoOption(ScheduleEvent):
    """
    create_todo_options와 함께 일정이 생성됨

    핸들러가 low-level로 Todo를 생성하므로 TodoDeadlineSet이 재발화하지
    않는다 (A→B→A 순환의 구조적 차단).

    :param tag_group_id: 생성될 Todo가 속할 TagGroup
    """
    tag_group_id: UUID
