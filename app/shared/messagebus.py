"""
In-process Message Bus (#54)

큐 방식 drain 루프로 이벤트를 핸들러에 전달합니다. 모든 핸들러는
같은 세션/트랜잭션에서 실행되며, 하나라도 실패하면 예외가 전파되어
전체 rollback됩니다 (doc §4.3).

- 누가 들을지는 중앙 registry(HANDLERS)가 정하며, 발행자는 모릅니다.
- cascade 무한루프 방지: event_key 중복 억제 + MAX_DISPATCH_DEPTH 상한.
- 핸들러 시그니처: (event, session) — 사용자 권한 검증을 우회하는 내부
  projection이므로, 변경 대상의 owner_id == event.owner_id 확인 후에만
  수정합니다 (doc §4.5).
"""
import logging
from typing import Callable, Dict, List, Sequence, Type

from sqlmodel import Session

from app.shared.events import DomainEvent
from app.shared.uow import drain_events

logger = logging.getLogger(__name__)

Handler = Callable[[DomainEvent, Session], None]

#: 한 drain 루프에서 처리할 수 있는 이벤트 수 상한 (폭주 cascade 차단)
MAX_DISPATCH_DEPTH = 10

#: 중앙 핸들러 registry — register()로만 등록
HANDLERS: Dict[Type[DomainEvent], List[Handler]] = {}


class MaxDispatchDepthExceededError(RuntimeError):
    """drain 루프가 MAX_DISPATCH_DEPTH를 초과 — 폭주 cascade 의심"""

    def __init__(self, event: DomainEvent):
        super().__init__(
            f"Max event dispatch depth ({MAX_DISPATCH_DEPTH}) exceeded "
            f"while handling {type(event).__qualname__}"
        )
        self.event = event


def register(event_type: Type[DomainEvent]):
    """
    핸들러 등록 데코레이터 — @register(TodoDeadlineSet)

    같은 (event_type, handler) 쌍은 한 번만 등록됩니다(idempotent) —
    모듈 재-import에 안전.
    """

    def decorator(fn: Handler) -> Handler:
        handlers = HANDLERS.setdefault(event_type, [])
        if fn not in handlers:
            handlers.append(fn)
        return fn

    return decorator


def handle(events: Sequence[DomainEvent], session: Session) -> None:
    """
    큐 방식 drain 루프 (doc §4.3)

    - event_key 중복은 skip (왕복 전파 종료)
    - 핸들러 실행 후 flush → 후속 핸들러가 앞선 변경을 조회 가능
    - 핸들러가 collect한 후속 이벤트를 재수집해 같은 루프에서 처리
    - 예외는 삼키지 않고 전파 → 호출자에서 전체 rollback
    """
    queue = list(events)
    seen: set = set()
    depth = 0

    while queue:
        event = queue.pop(0)

        key = event.event_key()
        if key in seen:
            logger.debug("Duplicate event suppressed in dispatch chain: %r", event)
            continue
        seen.add(key)

        if depth >= MAX_DISPATCH_DEPTH:
            raise MaxDispatchDepthExceededError(event)
        depth += 1

        for handler in HANDLERS.get(type(event), []):
            handler(event, session)

        session.flush()
        queue.extend(drain_events(session))


def register_handlers() -> None:
    """
    도메인 핸들러 모듈 일괄 등록 (idempotent)

    앱 startup(lifespan)과 테스트 fixture 양쪽에서 호출됩니다 (doc §4.3).
    consumer 모듈의 @register 부작용으로 등록되며, register()의 중복
    방지로 재호출에 안전합니다. 순환 import 방지를 위해 lazy import.
    """
    import app.domain.schedule.event_handlers  # noqa: F401


def reset_handlers() -> None:
    """registry 초기화 — 테스트 전용"""
    HANDLERS.clear()
