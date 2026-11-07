"""
타이머 실시간 이벤트

TimerService와 연결 타이머 핸들러(app/domain/timer/event_handlers.py)가 변경을 flush한 뒤
이벤트를 커밋 후 큐(app/shared/uow.py)에 적재한다. 루트 트랜잭션이 커밋되면 publisher가
받는 사람에게 보낸다.

- type: timer.created(start), timer.updated(pause·resume·stop·cancel·update), timer.deleted(delete)
- 연결된 Todo·Schedule 삭제로 링크가 끊기면 update, 함께 삭제되면 delete
- payload: action, actor_name(행위자 표시명), timer(TimerData, UTC aware). 삭제는 timer가 null이고 timer_id가 있다
- timer.elapsed_time은 저장값이다. RUNNING이면 클라이언트가 now - started_at을 더한다

계약: docs/api/websocket.ko.md
테스트: tests/domain/timer/test_realtime_events.py
"""
from datetime import UTC
from uuid import UUID

from sqlmodel import Session

from app.core.auth import CurrentUser
from app.domain.timer.model import TimerSession
from app.domain.timer.schema.ws import TimerAction, TimerData, TimerWSMessageType
from app.domain.visibility.enums import ResourceType
from app.domain.visibility.service import VisibilityService
from app.shared.uow import enqueue_after_commit
from app.websocket.base import WSServerMessage

_MESSAGE_TYPES = {
    TimerAction.START: TimerWSMessageType.CREATED,
    TimerAction.DELETE: TimerWSMessageType.DELETED,
}


def realtime_recipients(session: Session, owner: CurrentUser, timer_id: UUID) -> set[str]:
    """소유자 본인(다른 기기)과 공개 범위상 실시간으로 받는 친구"""
    return {owner.sub} | VisibilityService(session, owner).get_realtime_recipients(
        ResourceType.TIMER, timer_id, owner.sub
    )


def build_timer_event(
        action: TimerAction,
        actor: CurrentUser,
        timer: TimerSession | None,
        timer_id: UUID,
) -> dict:
    """봉투 dict (JSON 그대로 보낼 수 있는 값)"""
    payload: dict = {
        "action": action.value,
        "actor_name": actor.name,
        "timer": TimerData.model_validate(timer).to_timezone(UTC).model_dump(mode="json") if timer else None,
    }
    if timer is None:
        payload["timer_id"] = str(timer_id)
    message = WSServerMessage(
        type=_MESSAGE_TYPES.get(action, TimerWSMessageType.UPDATED).value,
        payload=payload,
        from_user=actor.sub,
    )
    return message.model_dump(mode="json")


def enqueue_timer_event(
        session: Session,
        actor: CurrentUser,
        action: TimerAction,
        users: set[str],
        timer: TimerSession | None = None,
        timer_id: UUID | None = None,
) -> None:
    """커밋되면 users에게 보낼 타이머 이벤트를 적재 (timer가 없으면 timer_id 필수)"""
    message = build_timer_event(action, actor, timer, timer.id if timer else timer_id)
    enqueue_after_commit(session, {"users": users, "message": message})
