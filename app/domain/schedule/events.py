"""
Schedule Domain Events

역전파(Schedule→Todo)는 `source_todo_id`가 있는 투영 일정에 한정된다.
"""
from dataclasses import dataclass
from typing import Optional, Tuple
from uuid import UUID

from app.domain.schedule.enums import SourceTodoPolicy
from app.domain.timer.enums import LinkedTimerPolicy
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

    Todo 쪽 흐름이 투영을 지울 때도 연결 타이머 정리를 위해 origin=TODO로 발행된다.

    :param source_todo_id: 삭제 직전 스냅샷 (row가 사라져 사후 조회 불가)
    :param policy: source-linked 일정이면 클라이언트가 명시한 source Todo
        처리 정책. unlinked 일정 삭제나 origin=TODO면 None
    :param linked_timer_ids: 삭제 직전 스냅샷한 연결 타이머 ID
        (`TimerSession.schedule_id`가 `ondelete=SET NULL`)
    :param linked_timer_policy: 클라이언트가 명시한 연결 타이머 처리 정책
    """
    source_todo_id: Optional[UUID]
    policy: Optional[SourceTodoPolicy]
    linked_timer_ids: Tuple[UUID, ...]
    linked_timer_policy: Optional[LinkedTimerPolicy] = None


@dataclass(frozen=True, kw_only=True)
class ScheduleUnlinkedFromTodo(ScheduleEvent):
    """
    일정이 마감 투영이기를 그만둠 (반복 전환으로 연결 해제)

    :param source_todo_id: 해제 직전 스냅샷
    :param policy: 클라이언트가 명시한 source Todo 처리 정책
    """
    source_todo_id: UUID
    policy: SourceTodoPolicy


@dataclass(frozen=True, kw_only=True)
class ScheduleCreatedWithTodoOption(ScheduleEvent):
    """
    create_todo_options와 함께 일정이 생성됨

    핸들러가 low-level로 Todo를 생성하므로 TodoDeadlineSet이 재발화하지
    않는다 (A→B→A 순환의 구조적 차단).

    :param tag_group_id: 생성될 Todo가 속할 TagGroup
    """
    tag_group_id: UUID
