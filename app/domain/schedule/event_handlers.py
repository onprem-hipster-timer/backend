"""
Schedule 측 Todo 이벤트 핸들러 (#55)

Todo 도메인의 사실(이벤트)을 받아 투영 Schedule을 동기화합니다.
변환 책임은 받는 쪽(이 모듈)에 있습니다.

원칙 (doc §4.5):
- 핸들러는 내부 projection이므로 사용자 권한 검증을 우회하는 대신
  **owner 불변조건**을 강제합니다: 변경 대상의 owner_id == event.owner_id.
- CurrentUser를 요구하는 Service를 호출하지 않고 owner_id 기반
  low-level 연산(crud, 모델 직접 조작)을 사용합니다.
- 자동 생성 리소스에 visibility를 복사하지 않습니다 (기본 PRIVATE).
- 삭제 시 delete_visibility_by_resource cleanup을 유지합니다.
"""
import logging
from datetime import timedelta
from uuid import UUID

from sqlmodel import Session

from app.crud import schedule as schedule_crud
from app.crud import tag as tag_crud
from app.crud import todo as todo_crud
from app.crud import visibility as visibility_crud
from app.domain.todo.events import (
    TodoDeadlineChanged,
    TodoDeadlineRemoved,
    TodoDeadlineSet,
    TodoDeleted,
    TodoTagsChanged,
)
from app.domain.visibility.enums import ResourceType
from app.models.schedule import Schedule
from app.models.todo import Todo
from app.shared.messagebus import register

logger = logging.getLogger(__name__)

#: 투영 Schedule 생성 시 초기 길이 (이후 길이는 Schedule 소유 — doc §5.1)
INITIAL_PROJECTION_DURATION = timedelta(hours=1)


def _get_owned_todo(session: Session, event) -> Todo | None:
    """owner 불변조건을 통과한 Todo 반환 (없으면 None)"""
    todo = todo_crud.get_todo(session, event.todo_id, event.owner_id)
    if todo is None:
        logger.warning(
            "Todo %s not found for %s (owner=%s) — skipping projection",
            event.todo_id, type(event).__qualname__, event.owner_id,
        )
    return todo


def _sync_projection_tags(session: Session, schedule_id: UUID, todo: Todo) -> None:
    """
    투영 Schedule 태그를 Todo 태그로 full-replace (D2 계약)

    owner 불변조건: 이벤트 소유자의 태그만 연결합니다.
    """
    tag_crud.delete_all_schedule_tags(session, schedule_id)
    for tag in todo.tags:
        if tag.owner_id == todo.owner_id:
            tag_crud.add_schedule_tag(session, schedule_id, tag.id)


def _delete_schedule_with_cleanup(session: Session, schedule: Schedule) -> None:
    """Schedule 삭제 + 접근권한 설정 cleanup (orphan visibility 방지)"""
    visibility_crud.delete_visibility_by_resource(
        session, ResourceType.SCHEDULE, schedule.id
    )
    schedule_crud.delete_schedule(session, schedule)


@register(TodoDeadlineSet)
def create_projection_schedule(event: TodoDeadlineSet, session: Session) -> None:
    """deadline 설정 → 투영 Schedule 생성 (제목·설명·태그는 Todo에서 투영)"""
    todo = _get_owned_todo(session, event)
    if todo is None or todo.deadline is None:
        return

    schedule = Schedule(
        owner_id=event.owner_id,
        title=todo.title,
        description=todo.description,
        start_time=todo.deadline,
        end_time=todo.deadline + INITIAL_PROJECTION_DURATION,
        source_todo_id=todo.id,
        # state는 모델 기본값 PLANNED, visibility는 복사하지 않음 (기본 PRIVATE)
    )
    session.add(schedule)
    session.flush()

    _sync_projection_tags(session, schedule.id, todo)


@register(TodoDeadlineChanged)
def move_projection_schedule(event: TodoDeadlineChanged, session: Session) -> None:
    """deadline 변경 → 투영 시작 시간 이동 (파리티: end = start + 1시간)"""
    todo = _get_owned_todo(session, event)
    if todo is None or todo.deadline is None:
        return

    schedules = schedule_crud.get_schedules_by_source_todo_id(
        session, event.todo_id, event.owner_id
    )
    if not schedules:
        return

    schedule = schedules[0]
    schedule.start_time = todo.deadline
    schedule.end_time = todo.deadline + INITIAL_PROJECTION_DURATION
    session.flush()

    _sync_projection_tags(session, schedule.id, todo)


@register(TodoDeadlineRemoved)
def remove_projection_schedule(event: TodoDeadlineRemoved, session: Session) -> None:
    """deadline 제거 → 투영 Schedule 삭제 + visibility cleanup"""
    schedules = schedule_crud.get_schedules_by_source_todo_id(
        session, event.todo_id, event.owner_id
    )
    for schedule in schedules:
        _delete_schedule_with_cleanup(session, schedule)


@register(TodoTagsChanged)
def sync_projection_tags(event: TodoTagsChanged, session: Session) -> None:
    """태그 변경 → 투영 Schedule 태그 full-replace (D2 계약)"""
    todo = _get_owned_todo(session, event)
    if todo is None:
        return

    schedules = schedule_crud.get_schedules_by_source_todo_id(
        session, event.todo_id, event.owner_id
    )
    for schedule in schedules:
        _sync_projection_tags(session, schedule.id, todo)


@register(TodoDeleted)
def remove_projections_of_deleted_todo(event: TodoDeleted, session: Session) -> None:
    """Todo 삭제 → 스냅샷된 연결 Schedule 삭제 + visibility cleanup"""
    schedules = schedule_crud.get_schedules_by_ids(
        session, list(event.linked_schedule_ids)
    )
    for schedule in schedules:
        # owner 불변조건 (doc §4.5)
        if schedule.owner_id != event.owner_id:
            logger.warning(
                "Schedule %s owner mismatch on TodoDeleted — skipping", schedule.id
            )
            continue
        _delete_schedule_with_cleanup(session, schedule)
