"""
Schedule Domain Events (#55 Phase B)

Schedule 변경 사실을 알리는 불변 이벤트. 역전파(Schedule→Todo)는
`source_todo_id`가 있는 투영 일정에 한정되며, 규칙은 필드 소유권 표
(docs/development/domain-events.ko.md §5.1)를 따릅니다.
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
    """
    일정 시간이 변경됨 → source-linked·비반복 일정이면 Todo.deadline 역투영

    origin이 TODO면 재전파하지 않습니다 (doc §4.4 왕복 차단).
    """


@dataclass(frozen=True, kw_only=True)
class ScheduleDeleted(ScheduleEvent):
    """
    일정이 삭제됨 → source Todo의 status를 투영 부재로 반영

    :param source_todo_id: 삭제 직전 스냅샷 (row가 사라져 사후 조회 불가).
        Todo·deadline은 유지됩니다 (#55 정책 — 삭제는 캘린더 표시 제거일 뿐).
    """
    source_todo_id: Optional[UUID]


@dataclass(frozen=True, kw_only=True)
class ScheduleCreatedWithTodoOption(ScheduleEvent):
    """
    create_todo_options와 함께 일정이 생성됨 → 연결 Todo 생성

    핸들러가 low-level로 Todo를 생성하므로 TodoDeadlineSet이 재발화하지
    않습니다 (A→B→A 구조적 차단; origin=SCHEDULE은 이중 안전장치).

    :param tag_group_id: 생성될 Todo가 속할 TagGroup
    """
    tag_group_id: UUID
