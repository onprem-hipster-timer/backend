"""
In-process Domain Event + Message Bus 테스트 (#54)

검증 항목:
- collect/drain/clear 세션 스코프 이벤트 큐
- 단일 트랜잭션 내 dispatch (등록 순서, (event, session) 시그니처)
- 핸들러 예외 전파 (삼키지 않음 → 전체 rollback 가능)
- cascade 재수집 (핸들러가 낳은 후속 이벤트 처리)
- 왕복(ping-pong) 이벤트 종료 (event_key 중복 억제)
- MAX_DISPATCH_DEPTH 초과 시 예외
- register 중복 등록 방지 (idempotent)
- rollback 경계에서 clear_events
"""
from dataclasses import dataclass

import pytest
from sqlmodel import Session

from app.shared import messagebus
from app.shared.events import DomainEvent, EventOrigin
from app.shared.messagebus import (
    HANDLERS,
    MAX_DISPATCH_DEPTH,
    MaxDispatchDepthExceededError,
    handle,
    register,
    reset_handlers,
)
from app.shared.uow import (
    clear_events,
    collect_event,
    commit_with_events,
    drain_events,
    flush_and_dispatch_events,
)


# ============================================================
# 테스트용 더미 이벤트
# ============================================================

@dataclass(frozen=True, kw_only=True)
class PingEvent(DomainEvent):
    ping_id: str

    def event_key(self) -> tuple:
        return ("PingEvent", self.ping_id)


@dataclass(frozen=True, kw_only=True)
class PongEvent(DomainEvent):
    pong_id: str

    def event_key(self) -> tuple:
        return ("PongEvent", self.pong_id)


@dataclass(frozen=True, kw_only=True)
class ChainEvent(DomainEvent):
    n: int

    def event_key(self) -> tuple:
        return ("ChainEvent", self.n)


def _ping(ping_id: str = "p1") -> PingEvent:
    return PingEvent(owner_id="user-1", origin=EventOrigin.TODO, ping_id=ping_id)


def _pong(pong_id: str = "q1") -> PongEvent:
    return PongEvent(owner_id="user-1", origin=EventOrigin.SCHEDULE, pong_id=pong_id)


# ============================================================
# fixtures
# ============================================================

@pytest.fixture(autouse=True)
def clean_handlers():
    """테스트 간 핸들러 레지스트리 격리"""
    snapshot = {k: list(v) for k, v in HANDLERS.items()}
    HANDLERS.clear()
    try:
        yield
    finally:
        HANDLERS.clear()
        HANDLERS.update(snapshot)


# ============================================================
# uow: collect / drain / clear
# ============================================================

class TestEventQueue:
    def test_collect_and_drain_in_order(self, test_session):
        e1, e2 = _ping("a"), _ping("b")
        collect_event(test_session, e1)
        collect_event(test_session, e2)

        drained = drain_events(test_session)

        assert drained == [e1, e2]
        assert drain_events(test_session) == []

    def test_clear_events(self, test_session):
        collect_event(test_session, _ping())
        clear_events(test_session)

        assert drain_events(test_session) == []

    def test_clear_events_on_empty_session_is_noop(self, test_session):
        clear_events(test_session)  # 수집 전 호출해도 에러 없음
        assert drain_events(test_session) == []

    def test_rollback_then_clear_removes_stale_events(self, test_engine):
        """session.info는 트랜잭션 aware가 아님 (doc §4.2) — rollback 경계에서 clear 필수"""
        with Session(test_engine) as session:
            collect_event(session, _ping())
            session.rollback()

            # rollback만으로는 큐가 비워지지 않음 (위험 문서화)
            assert len(session.info.get("domain_events", [])) == 1

            clear_events(session)
            assert drain_events(session) == []


# ============================================================
# messagebus: register
# ============================================================

class TestRegister:
    def test_register_adds_handler(self):
        @register(PingEvent)
        def on_ping(event, session):
            pass

        assert HANDLERS[PingEvent] == [on_ping]

    def test_register_is_idempotent(self):
        def on_ping(event, session):
            pass

        register(PingEvent)(on_ping)
        register(PingEvent)(on_ping)

        assert HANDLERS[PingEvent] == [on_ping]

    def test_reset_handlers(self):
        @register(PingEvent)
        def on_ping(event, session):
            pass

        reset_handlers()
        assert HANDLERS == {}


# ============================================================
# messagebus: handle (drain loop)
# ============================================================

class TestHandle:
    def test_dispatches_to_handlers_in_registration_order(self, test_session):
        calls = []

        @register(PingEvent)
        def first(event, session):
            calls.append(("first", event, session))

        @register(PingEvent)
        def second(event, session):
            calls.append(("second", event, session))

        event = _ping()
        handle([event], test_session)

        assert [c[0] for c in calls] == ["first", "second"]
        assert all(c[1] is event for c in calls)
        assert all(c[2] is test_session for c in calls)

    def test_event_without_handlers_is_noop(self, test_session):
        handle([_ping()], test_session)  # 에러 없음

    def test_empty_events_is_noop(self, test_session):
        handle([], test_session)

    def test_handler_exception_propagates(self, test_session):
        """예외를 삼키지 않음 → 호출자에서 전체 rollback (doc §2)"""

        @register(PingEvent)
        def broken(event, session):
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            handle([_ping()], test_session)

    def test_cascade_events_are_recollected(self, test_session):
        """핸들러가 collect한 후속 이벤트도 같은 drain 루프에서 처리"""
        calls = []

        @register(PingEvent)
        def on_ping(event, session):
            calls.append("ping")
            collect_event(session, _pong())

        @register(PongEvent)
        def on_pong(event, session):
            calls.append("pong")

        handle([_ping()], test_session)

        assert calls == ["ping", "pong"]

    def test_pingpong_terminates_with_dedupe(self, test_session):
        """왕복 전파(A→B→A)는 event_key 중복 억제로 종료 — 각 핸들러 1회만 실행"""
        calls = []

        @register(PingEvent)
        def on_ping(event, session):
            calls.append("ping")
            collect_event(session, _pong("q1"))

        @register(PongEvent)
        def on_pong(event, session):
            calls.append("pong")
            collect_event(session, _ping("p1"))

        handle([_ping("p1")], test_session)

        assert calls == ["ping", "pong"]

    def test_depth_limit_raises(self, test_session):
        """서로 다른 이벤트가 한없이 이어지는 폭주 cascade는 depth 상한에서 차단"""

        @register(ChainEvent)
        def on_chain(event, session):
            collect_event(
                session,
                ChainEvent(owner_id="user-1", origin=EventOrigin.TODO, n=event.n + 1),
            )

        with pytest.raises(MaxDispatchDepthExceededError):
            handle(
                [ChainEvent(owner_id="user-1", origin=EventOrigin.TODO, n=0)],
                test_session,
            )

    def test_depth_limit_allows_reasonable_chains(self, test_session):
        """상한 이내의 정상 체인은 통과"""
        calls = []
        limit = MAX_DISPATCH_DEPTH - 1

        @register(ChainEvent)
        def on_chain(event, session):
            calls.append(event.n)
            if event.n < limit:
                collect_event(
                    session,
                    ChainEvent(owner_id="user-1", origin=EventOrigin.TODO, n=event.n + 1),
                )

        handle(
            [ChainEvent(owner_id="user-1", origin=EventOrigin.TODO, n=0)],
            test_session,
        )

        assert calls == list(range(limit + 1))


# ============================================================
# uow: flush_and_dispatch_events / commit_with_events
# ============================================================

class TestFlushAndDispatch:
    def test_dispatches_collected_events(self, test_session):
        calls = []

        @register(PingEvent)
        def on_ping(event, session):
            calls.append(event)

        collect_event(test_session, _ping())
        flush_and_dispatch_events(test_session)

        assert len(calls) == 1
        assert drain_events(test_session) == []

    def test_noop_without_events(self, test_session):
        flush_and_dispatch_events(test_session)  # 에러 없음

    def test_commit_with_events_dispatches_then_commits(self, test_engine):
        """안전망: commit 직전 미처리 이벤트를 drain 후 commit"""
        calls = []

        @register(PingEvent)
        def on_ping(event, session):
            calls.append(event)

        with Session(test_engine) as session:
            collect_event(session, _ping())
            commit_with_events(session)

        assert len(calls) == 1

    def test_commit_with_events_propagates_handler_error(self, test_engine):
        @register(PingEvent)
        def broken(event, session):
            raise RuntimeError("handler failed")

        with Session(test_engine) as session:
            collect_event(session, _ping())
            with pytest.raises(RuntimeError, match="handler failed"):
                commit_with_events(session)


# ============================================================
# register_handlers / bootstrap
# ============================================================

class TestRegisterHandlers:
    def test_register_handlers_is_idempotent(self):
        """앱 startup·테스트 fixture 양쪽에서 호출되므로 중복 호출 안전 (doc §4.3)"""
        messagebus.register_handlers()
        first = {k: list(v) for k, v in HANDLERS.items()}

        messagebus.register_handlers()

        assert {k: list(v) for k, v in HANDLERS.items()} == first
