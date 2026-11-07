"""
Timer Domain Events

연결 Todo의 상태 전파에 쓴다 (핸들러: app/domain/todo/event_handlers.py).
"""
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from app.shared.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class TimerEvent(DomainEvent):
    """
    Timer 이벤트 공통 베이스 — event_key에 timer_id 포함

    :param todo_id: 연결 Todo ID. 연결이 없으면 None
    """
    timer_id: UUID
    todo_id: Optional[UUID]

    def event_key(self) -> tuple:
        return (type(self).__qualname__, str(self.timer_id))


@dataclass(frozen=True, kw_only=True)
class TimerCompleted(TimerEvent):
    """타이머가 완료됨 (COMPLETED)"""


@dataclass(frozen=True, kw_only=True)
class TimerCancelled(TimerEvent):
    """타이머가 취소됨 (CANCELLED)"""
