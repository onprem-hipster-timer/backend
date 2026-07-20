"""
Schedule 이벤트를 받아 source Todo를 동기화하는 핸들러.

역투영은 source_todo_id가 있는 일정에 한정하며, origin이 TODO인 변경은
재전파하지 않는다. status는 직접 쓰기(이벤트 미발행)로 갱신해 drain
재수집을 막는다.
"""
import logging

from sqlmodel import Session

from app.crud import schedule as schedule_crud
from app.crud import tag as tag_crud
from app.crud import todo as todo_crud
from app.domain.schedule.events import (
    ScheduleCreatedWithTodoOption,
    ScheduleDeleted,
    ScheduleTimeChanged,
)
from app.domain.todo.enums import TodoStatus
from app.models.todo import Todo
from app.shared.events import EventOrigin
from app.shared.messagebus import register

logger = logging.getLogger(__name__)


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
def reset_status_of_source_todo(event: ScheduleDeleted, session: Session) -> None:
    """투영 삭제 → Todo·deadline 유지, status만 투영 부재 반영"""
    if event.origin == EventOrigin.TODO:
        return  # Todo발 삭제/정리는 Todo 쪽 흐름이 이미 상태를 관리
    if event.source_todo_id is None:
        return

    todo = todo_crud.get_todo(session, event.source_todo_id, event.owner_id)
    if todo is None:
        return

    # 터미널 상태(DONE/CANCELLED)는 덮지 않음 — 자동화는 SCHEDULED에만 작용
    if todo.status == TodoStatus.SCHEDULED:
        todo.status = TodoStatus.UNSCHEDULED
        session.flush()


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
        tag_group_id=event.tag_group_id,
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
