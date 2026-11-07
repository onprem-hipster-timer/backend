"""
Todo·Schedule 삭제 이벤트를 받아 연결 타이머를 처리하는 핸들러.

연결 타이머는 클라이언트가 지정한 linked_timer_policy로 처리한다. 연결 타이머가
있는데 정책이 없으면 LinkedTimerPolicyRequiredError(422)를 던져 요청 전체를
rollback한다. 핸들러는 owner 불변조건을 강제하고 low-level 연산만 쓰며, 바뀐
타이머는 커밋 후 큐에 실시간 이벤트로 적재한다 (rollback되면 버려진다).

Todo 쪽 흐름(마감 제거, Todo 삭제의 linked_schedule_policy=delete)이 투영 일정을
지우면 그 일정에 걸린 타이머는 묻지 않고 schedule_id만 잃는다(origin=TODO, 정책 없음).
삭제되는 Todo에도 연결된 타이머는 그 Todo의 linked_timer_policy만 따르고, 이벤트는
타이머마다 하나다.
"""
from typing import Iterable
from uuid import UUID

from sqlmodel import Session

from app.core.auth import CurrentUser
from app.crud import timer as timer_crud
from app.crud import user_profile as user_profile_crud
from app.crud import visibility as visibility_crud
from app.domain.schedule.events import ScheduleDeleted
from app.domain.timer.enums import LinkedTimerPolicy
from app.domain.timer.exceptions import LinkedTimerPolicyRequiredError
from app.domain.timer.model import TimerSession
from app.domain.timer.realtime import enqueue_timer_event, realtime_recipients
from app.domain.timer.schema.ws import TimerAction
from app.domain.todo.enums import LinkedSchedulePolicy
from app.domain.todo.events import TodoDeleted
from app.domain.visibility.enums import ResourceType
from app.models.base import utc_now_naive
from app.shared.events import EventOrigin
from app.shared.messagebus import register


# ============================================================
# 내부 helper
# ============================================================

def _owned_timers(session: Session, timer_ids: Iterable[UUID], owner_id: str) -> list[TimerSession]:
    """스냅샷된 타이머 중 남아 있고 owner 불변조건을 통과한 것"""
    timers = timer_crud.get_timers_by_ids(session, list(timer_ids))
    return [timer for timer in timers if timer.owner_id == owner_id]


def _actor(session: Session, owner_id: str) -> CurrentUser:
    """실시간 이벤트의 행위자 — 삭제를 요청한 소유자. 표시명은 요청마다 동기화되는 프로필에서"""
    profile = user_profile_crud.get_by_sub(session, owner_id)
    return CurrentUser(sub=owner_id, name=profile.display_name if profile else None)


def _delete_timer(session: Session, actor: CurrentUser, timer: TimerSession) -> None:
    """타이머 삭제 + 접근권한 설정 cleanup. 받는 사람은 cleanup 전에 계산한다"""
    timer_id = timer.id
    recipients = realtime_recipients(session, actor, timer_id)
    visibility_crud.delete_visibility_by_resource(session, ResourceType.TIMER, timer_id)
    timer_crud.delete_timer(session, timer)
    enqueue_timer_event(session, actor, TimerAction.DELETE, recipients, timer_id=timer_id)


def _publish_unlinked(session: Session, actor: CurrentUser, timer: TimerSession) -> None:
    """연결 해제를 updated_at에 반영하고 timer.updated(update)를 적재. 상태(실행 중 등)는 그대로"""
    timer.updated_at = utc_now_naive()
    session.flush()
    enqueue_timer_event(
        session, actor, TimerAction.UPDATE, realtime_recipients(session, actor, timer.id), timer=timer
    )


# ============================================================
# 핸들러
# ============================================================

@register(TodoDeleted)
def apply_policy_to_timers_of_deleted_todo(event: TodoDeleted, session: Session) -> None:
    """Todo 삭제 → 스냅샷된 연결 타이머를 클라이언트 정책에 따라 삭제 또는 연결 해제"""
    timers = _owned_timers(session, event.linked_timer_ids, event.owner_id)
    if not timers:
        return
    if event.linked_timer_policy is None:
        raise LinkedTimerPolicyRequiredError()

    # 함께 삭제되는 투영 일정의 연결도 여기서 끊는다 (투영 쪽 ScheduleDeleted는 이 타이머를 제외)
    deleted_projection_ids = (
        set(event.linked_schedule_ids) if event.policy == LinkedSchedulePolicy.DELETE else set()
    )
    actor = _actor(session, event.owner_id)
    for timer in timers:
        if event.linked_timer_policy == LinkedTimerPolicy.DELETE:
            _delete_timer(session, actor, timer)
        else:
            timer.todo_id = None
            if timer.schedule_id in deleted_projection_ids:
                timer.schedule_id = None
            _publish_unlinked(session, actor, timer)


@register(ScheduleDeleted)
def apply_policy_to_timers_of_deleted_schedule(event: ScheduleDeleted, session: Session) -> None:
    """
    Schedule 삭제 → 스냅샷된 연결 타이머를 클라이언트 정책에 따라 삭제 또는 일정 연결만 해제

    Todo 쪽 흐름이 지운 투영(origin=TODO)은 정책 없이 일정 연결만 해제한다.
    """
    timers = _owned_timers(session, event.linked_timer_ids, event.owner_id)
    if not timers:
        return
    policy = event.linked_timer_policy
    if policy is None:
        if event.origin != EventOrigin.TODO:
            raise LinkedTimerPolicyRequiredError()
        policy = LinkedTimerPolicy.UNLINK

    actor = _actor(session, event.owner_id)
    for timer in timers:
        if policy == LinkedTimerPolicy.DELETE:
            _delete_timer(session, actor, timer)
        else:
            timer.schedule_id = None
            _publish_unlinked(session, actor, timer)
