"""
In-process Message Bus

큐 방식 drain 루프로 이벤트를 핸들러에 전달한다. 모든 핸들러는 같은
세션/트랜잭션에서 실행되며, 하나라도 실패하면 예외가 전파되어 전체
rollback된다. cascade 무한루프는 event_key 중복 억제와
MAX_DISPATCH_DEPTH 상한으로 차단한다.
"""
import logging
from typing import Callable, Dict, List, Sequence, Type

from sqlmodel import Session

from app.shared.events import DomainEvent
from app.shared.uow import drain_events

logger = logging.getLogger(__name__)

Handler = Callable[[DomainEvent, Session], None]

#: 한 drain 루프에서 처리하는 **총 이벤트 수** 상한 (폭주 cascade 차단).
#: 재귀 깊이가 아니다 — 배치성 대량 발행이 필요해지면 깊이/총량 분리 필요.
MAX_DISPATCH_DEPTH = 10

#: 중앙 핸들러 registry — register()로만 등록
HANDLERS: Dict[Type[DomainEvent], List[Handler]] = {}

#: @register가 기록하는 등록 명세. 모듈 import는 한 번만 데코레이터를
#: 실행하므로, reset_handlers() 이후 register_handlers()가 이 명세를
#: replay해 registry를 복구한다.
_KNOWN_REGISTRATIONS: List[tuple] = []


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

    같은 (event_type, handler) 쌍은 한 번만 등록된다(idempotent) —
    모듈 재-import에 안전.
    """

    def decorator(fn: Handler) -> Handler:
        if (event_type, fn) not in _KNOWN_REGISTRATIONS:
            _KNOWN_REGISTRATIONS.append((event_type, fn))
        _add_handler(event_type, fn)
        return fn

    return decorator


def _add_handler(event_type: Type[DomainEvent], fn: Handler) -> None:
    handlers = HANDLERS.setdefault(event_type, [])
    if fn not in handlers:
        handlers.append(fn)


def handle(events: Sequence[DomainEvent], session: Session) -> None:
    """
    큐 방식 drain 루프

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
    도메인 핸들러 일괄 등록 (idempotent, reset 후 복구 가능)

    앱 startup(lifespan)과 테스트 fixture 양쪽에서 호출되므로 재호출에
    안전해야 한다. import는 첫 호출에서만 데코레이터를 실행하므로,
    기록된 등록 명세를 replay해 reset_handlers() 이후에도 복구한다.
    순환 import 방지를 위해 lazy import.
    """
    import app.domain.schedule.event_handlers  # noqa: F401
    import app.domain.todo.event_handlers  # noqa: F401

    for event_type, fn in _KNOWN_REGISTRATIONS:
        _add_handler(event_type, fn)


def reset_handlers() -> None:
    """registry 초기화 — 테스트 전용. register_handlers()로 복구할 수 있다."""
    HANDLERS.clear()
