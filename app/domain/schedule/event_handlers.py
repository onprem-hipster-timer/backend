"""
Todo 이벤트를 받아 투영 Schedule을 동기화하는 핸들러.

핸들러는 내부 projection이라 사용자 권한 검증 대신 owner 불변조건
(변경 대상 owner_id == event.owner_id)을 강제하고, CurrentUser 없이
low-level 연산만 사용한다. 자동 생성 리소스에 visibility는 복사하지 않는다.
"""
import logging
from datetime import timedelta
from uuid import UUID

from sqlmodel import Session

from app.crud import schedule as schedule_crud
from app.crud import tag as tag_crud
from app.crud import todo as todo_crud
from app.crud import visibility as visibility_crud
from app.domain.todo.enums import LinkedSchedulePolicy
from app.domain.todo.events import (
    TodoContentChanged,
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

#: 투영 생성 시 초기 길이. 이후 길이는 사용자가 조정할 수 있고
#: deadline 이동 시 보존된다.
INITIAL_PROJECTION_DURATION = timedelta(hours=1)


# ============================================================
# 내부 helper
# ============================================================

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
    """투영 태그를 Todo 태그로 전체 교체. 소유자의 태그만 연결한다."""
    tag_crud.delete_all_schedule_tags(session, schedule_id)
    for tag in todo.tags:
        if tag.owner_id == todo.owner_id:
            tag_crud.add_schedule_tag(session, schedule_id, tag.id)


def _create_projection(session: Session, todo: Todo) -> Schedule:
    """투영 Schedule 생성 — 제목·설명·태그는 Todo에서, 길이는 초기값"""
    schedule = Schedule(
        owner_id=todo.owner_id,
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
    return schedule


def _move_projection(session: Session, schedule: Schedule, todo: Todo) -> None:
    """start만 이동하고 사용자가 조정한 길이는 보존한다."""
    duration = schedule.end_time - schedule.start_time
    schedule.start_time = todo.deadline
    schedule.end_time = todo.deadline + duration
    session.flush()


def _delete_schedule_with_cleanup(session: Session, schedule: Schedule) -> None:
    """Schedule 삭제 + 접근권한 설정 cleanup (orphan visibility 방지)"""
    visibility_crud.delete_visibility_by_resource(
        session, ResourceType.SCHEDULE, schedule.id
    )
    schedule_crud.delete_schedule(session, schedule)


def _unlink_schedule(session: Session, schedule: Schedule) -> None:
    """연결만 해제 — 일반 일정으로 생존 (메모·태그·공유 보존)"""
    schedule.source_todo_id = None
    session.flush()


# ============================================================
# 핸들러
# ============================================================

@register(TodoDeadlineSet)
def create_projection_schedule(event: TodoDeadlineSet, session: Session) -> None:
    """deadline 설정 → 투영 생성. 이미 있으면 이동 (단일 투영 불변조건)"""
    todo = _get_owned_todo(session, event)
    if todo is None or todo.deadline is None:
        return

    schedules = schedule_crud.get_schedules_by_source_todo_id(
        session, event.todo_id, event.owner_id
    )
    if schedules:
        _move_projection(session, schedules[0], todo)
    else:
        _create_projection(session, todo)


@register(TodoDeadlineChanged)
def move_projection_schedule(event: TodoDeadlineChanged, session: Session) -> None:
    """deadline 변경 → 투영 이동. 투영이 없으면 재생성 (조용한 no-op 금지)"""
    todo = _get_owned_todo(session, event)
    if todo is None or todo.deadline is None:
        return

    schedules = schedule_crud.get_schedules_by_source_todo_id(
        session, event.todo_id, event.owner_id
    )
    if schedules:
        _move_projection(session, schedules[0], todo)
    else:
        _create_projection(session, todo)


@register(TodoDeadlineRemoved)
def remove_projection_schedule(event: TodoDeadlineRemoved, session: Session) -> None:
    """deadline 제거 → 클라이언트 정책에 따라 삭제 또는 연결 해제"""
    schedules = schedule_crud.get_schedules_by_source_todo_id(
        session, event.todo_id, event.owner_id
    )
    for schedule in schedules:
        if event.policy == LinkedSchedulePolicy.UNLINK:
            _unlink_schedule(session, schedule)
        else:
            _delete_schedule_with_cleanup(session, schedule)


@register(TodoContentChanged)
def sync_projection_content(event: TodoContentChanged, session: Session) -> None:
    """제목·설명 변경 → 투영에 최신 내용 반영"""
    todo = _get_owned_todo(session, event)
    if todo is None:
        return

    schedules = schedule_crud.get_schedules_by_source_todo_id(
        session, event.todo_id, event.owner_id
    )
    for schedule in schedules:
        schedule.title = todo.title
        schedule.description = todo.description
    if schedules:
        session.flush()


@register(TodoTagsChanged)
def sync_projection_tags(event: TodoTagsChanged, session: Session) -> None:
    """태그 변경 → 투영 태그 전체 교체"""
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
    """Todo 삭제 → 스냅샷된 연결 투영을 클라이언트 정책에 따라 처리"""
    schedules = schedule_crud.get_schedules_by_ids(
        session, list(event.linked_schedule_ids)
    )
    for schedule in schedules:
        if schedule.owner_id != event.owner_id:  # owner 불변조건
            logger.warning(
                "Schedule %s owner mismatch on TodoDeleted — skipping", schedule.id
            )
            continue
        if event.policy == LinkedSchedulePolicy.UNLINK:
            _unlink_schedule(session, schedule)
        else:
            _delete_schedule_with_cleanup(session, schedule)
