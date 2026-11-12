"""
Schedule·Timer 이벤트를 받아 Todo를 동기화하는 핸들러.

역투영은 source_todo_id가 있는 일정에 한정하며, origin이 TODO인 변경은
재전파하지 않는다. 타이머 완료·취소는 연결 Todo를 DONE·CANCELLED로 바꾸고,
이미 DONE·CANCELLED인 Todo는 덮지 않는다.

status를 바꾸면 연결 타이머를 위해 TodoStatusChanged를 수집한다. 타이머 핸들러는 Todo를
다시 바꾸지 않으므로(완료·취소가 수집하는 TimerCompleted·TimerCancelled는 Todo가 이미
터미널 상태라 여기서 무시된다) 왕복은 한 번에 끝난다.
"""
import logging

from sqlmodel import Session

from app.crud import schedule as schedule_crud
from app.crud import tag as tag_crud
from app.crud import todo as todo_crud
from app.domain.schedule.enums import SourceTodoPolicy
from app.domain.schedule.events import (
    ScheduleCreatedWithTodoOption,
    ScheduleDeleted,
    ScheduleTimeChanged,
    ScheduleUnlinkedFromTodo,
)
from app.domain.timer.events import TimerCancelled, TimerCompleted, TimerEvent
from app.domain.todo.enums import TodoStatus
from app.domain.todo.events import TodoStatusChanged
from app.models.todo import Todo
from app.shared.events import EventOrigin
from app.shared.messagebus import register
from app.shared.uow import collect_event

logger = logging.getLogger(__name__)


def _change_status(session: Session, todo: Todo, status: TodoStatus, origin: EventOrigin) -> None:
    """status를 바꾸고 TodoStatusChanged 수집 (호출자가 실제 전이인지 확인한다)"""
    todo.status = status
    collect_event(session, TodoStatusChanged(
        owner_id=todo.owner_id,
        origin=origin,
        todo_id=todo.id,
        status=status,
    ))


def _apply_detach_policy(
        session: Session, todo: Todo, policy: SourceTodoPolicy, origin: EventOrigin
) -> None:
    """투영이 사라진 Todo에 클라이언트 정책 적용 + 연동 플래그 해제"""
    if policy == SourceTodoPolicy.CLEAR_DEADLINE:
        todo.deadline = None
    # 터미널 상태(DONE/CANCELLED)는 덮지 않음 — 플래그 해제는 SCHEDULED에만
    if todo.status == TodoStatus.SCHEDULED:
        _change_status(session, todo, TodoStatus.UNSCHEDULED, origin)
    session.flush()


def _finish_linked_todo(session: Session, event: TimerEvent, status: TodoStatus) -> None:
    """타이머의 연결 Todo를 터미널 상태로. 이미 DONE·CANCELLED면 그대로 둔다"""
    if event.todo_id is None:
        return
    todo = todo_crud.get_todo(session, event.todo_id, event.owner_id)
    if todo is None or todo.status in (TodoStatus.DONE, TodoStatus.CANCELLED):
        return
    _change_status(session, todo, status, event.origin)
    session.flush()


@register(ScheduleTimeChanged)
def backpropagate_deadline(event: ScheduleTimeChanged, session: Session) -> None:
    """투영 일정 시간 이동 → Todo.deadline 역투영"""
    if event.origin == EventOrigin.TODO:
        return  # Todo발 변경의 재전파 차단

    schedule = schedule_crud.get_schedule(session, event.schedule_id, event.owner_id)
    if schedule is None or schedule.source_todo_id is None:
        return
    if schedule.recurrence_rule:
        # 반복 일정이 된 투영은 시점 마감의 투영이 아님 — 역투영 제외
        logger.debug(
            "Skipping deadline back-propagation for recurring schedule %s",
            schedule.id,
        )
        return

    todo = todo_crud.get_todo(session, schedule.source_todo_id, event.owner_id)
    if todo is None:
        return

    todo.deadline = schedule.start_time
    session.flush()


@register(ScheduleDeleted)
def apply_policy_on_projection_deleted(event: ScheduleDeleted, session: Session) -> None:
    """투영 삭제 → 클라이언트 정책에 따라 deadline 처리 + 연동 플래그 해제"""
    if event.origin == EventOrigin.TODO:
        return  # Todo발 삭제/정리는 Todo 쪽 흐름이 이미 상태를 관리
    if event.source_todo_id is None:
        return

    todo = todo_crud.get_todo(session, event.source_todo_id, event.owner_id)
    if todo is None:
        return

    # 내부 자동 삭제 경로는 policy가 없을 수 있음 → 데이터 보존 쪽 선택
    _apply_detach_policy(session, todo, event.policy or SourceTodoPolicy.KEEP_DEADLINE, event.origin)


@register(ScheduleUnlinkedFromTodo)
def apply_policy_on_projection_unlinked(
        event: ScheduleUnlinkedFromTodo, session: Session
) -> None:
    """반복 전환으로 연결 해제 → 클라이언트 정책에 따라 deadline 처리 + 플래그 해제"""
    todo = todo_crud.get_todo(session, event.source_todo_id, event.owner_id)
    if todo is None:
        return

    _apply_detach_policy(session, todo, event.policy, event.origin)


@register(ScheduleCreatedWithTodoOption)
def create_todo_for_schedule(
        event: ScheduleCreatedWithTodoOption, session: Session
) -> None:
    """
    create_todo_options → 연결 Todo 생성 + 역연결

    low-level 생성이므로 TodoDeadlineSet이 재발화하지 않는다
    (A→B→A 순환의 구조적 차단). 태그는 Schedule에서 복사한다.
    """
    schedule = schedule_crud.get_schedule(session, event.schedule_id, event.owner_id)
    if schedule is None or schedule.source_todo_id is not None:
        return

    todo = Todo(
        owner_id=event.owner_id,
        title=schedule.title,
        description=schedule.description,
        deadline=schedule.start_time,
        todo_group_id=event.todo_group_id,
        parent_id=None,
        status=TodoStatus.SCHEDULED,  # 투영(이 Schedule)이 있으므로 SCHEDULED
    )
    session.add(todo)
    session.flush()

    # 태그 복사 (owner 불변조건: 이벤트 소유자의 태그만)
    for tag in schedule.tags:
        if tag.owner_id == event.owner_id:
            tag_crud.add_todo_tag(session, todo.id, tag.id)

    schedule.source_todo_id = todo.id
    session.flush()


@register(TimerCompleted)
def complete_todo_of_completed_timer(event: TimerCompleted, session: Session) -> None:
    """타이머 완료 → 연결 Todo DONE"""
    _finish_linked_todo(session, event, TodoStatus.DONE)


@register(TimerCancelled)
def cancel_todo_of_cancelled_timer(event: TimerCancelled, session: Session) -> None:
    """타이머 취소 → 연결 Todo CANCELLED"""
    _finish_linked_todo(session, event, TodoStatus.CANCELLED)
