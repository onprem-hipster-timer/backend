"""
세션 스코프 이벤트 수집 helper

범용 이벤트 버스/outbox가 아니라 **동기 트랜잭션 내 도메인 이벤트 투영
큐**다 — 안전 보장은 "동기 요청 · 같은 세션 · DB 행만 갱신하는 핸들러"
범위에 한정된다 (적용 범위·경계: docs/development/domain-events.ko.md §4.5).

도메인 모델이 SQLModel ORM 클래스의 alias라 엔티티에 `.events` 리스트를
직접 붙일 수 없어, 세션 스코프 수집(`session.info`)을 사용한다.

!!! important
    `session.info`는 트랜잭션 aware가 아니다 — DB rollback이 돼도 이벤트
    큐가 자동으로 비워지지 않는다. rollback 경계에서 반드시
    `clear_events(session)`를 호출해야 한다.

이 모듈의 helper로만 큐에 접근한다 (`session.info` 직접 접근 금지).

## 커밋 후 큐 (`enqueue_after_commit`)

도메인 이벤트 큐와 별개다. 도메인 이벤트는 커밋 **전에** 같은 트랜잭션 안에서
처리되고, 이 큐의 항목은 루트 트랜잭션이 **커밋된 뒤에만** sink
(`set_after_commit_sink`, 실시간 publisher)로 넘어간다.

- 루트 커밋 → 항목을 순서대로 sink에 넘긴다. sink 예외는 로그만 남기고 삼킨다
  (이미 커밋된 요청을 실패시키지 않는다).
- key를 주고 적재하면 같은 key로 먼저 적재된 항목은 빠진다 (마지막 것만 나간다).
- 루트 rollback·close → 항목을 버린다.
- SAVEPOINT(`begin_nested`)의 커밋·rollback은 큐를 건드리지 않는다.
  그래서 SAVEPOINT 안에서 enqueue하면 안 된다 — SAVEPOINT만 rollback돼도
  항목이 남아 외부 커밋 때 나간다.

테스트: tests/shared/test_after_commit.py
"""
import logging
from typing import TYPE_CHECKING, Callable, Hashable, List

from sqlalchemy import event
from sqlmodel import Session

if TYPE_CHECKING:
    from app.shared.events import DomainEvent

logger = logging.getLogger(__name__)

_EVENTS_KEY = "domain_events"
_AFTER_COMMIT_KEY = "after_commit"

AfterCommitSink = Callable[[dict], None]


def _discard(item: dict) -> None:
    """sink가 설정되지 않았을 때 (테스트, 실시간 비활성)"""


_after_commit_sink: AfterCommitSink = _discard


def collect_event(session: Session, event: "DomainEvent") -> None:
    """이벤트를 세션 큐에 적재 (dispatch는 flush_and_dispatch_events에서)"""
    session.info.setdefault(_EVENTS_KEY, []).append(event)


def drain_events(session: Session) -> List["DomainEvent"]:
    """수집된 이벤트를 전부 꺼내 반환 (큐는 비워짐)"""
    events = session.info.get(_EVENTS_KEY, [])
    session.info[_EVENTS_KEY] = []
    return events


def clear_events(session: Session) -> None:
    """이벤트 큐 비우기 — rollback 경계에서 필수 호출"""
    session.info[_EVENTS_KEY] = []


def flush_and_dispatch_events(session: Session) -> None:
    """
    flush → drain/handle 루프 → flush (commit 없음)

    쓰기 use-case가 응답 DTO를 조립하기 전에 호출해야 핸들러가 만든
    자동 생성 리소스가 응답에 즉시 보인다. 핸들러 예외는 전파된다 →
    호출자(트랜잭션 경계)에서 전체 rollback.
    """
    from app.shared import messagebus

    session.flush()
    events = drain_events(session)
    if events:
        messagebus.handle(events, session)
    session.flush()


def commit_with_events(session: Session) -> None:
    """미처리 이벤트 dispatch를 한 번 더 보장(안전망)한 뒤 commit"""
    flush_and_dispatch_events(session)
    session.commit()


def enqueue_after_commit(session: Session, item: dict, key: Hashable | None = None) -> None:
    """
    루트 트랜잭션이 커밋되면 sink로 넘길 항목을 적재 (SAVEPOINT 안에서 호출 금지)

    key가 있으면 같은 key로 먼저 적재된 항목을 빼고 새 항목을 뒤에 둔다.
    """
    pending = session.info.setdefault(_AFTER_COMMIT_KEY, [])
    if key is not None:
        pending[:] = [entry for entry in pending if entry[0] != key]
    pending.append((key, item))


def set_after_commit_sink(sink: AfterCommitSink | None) -> AfterCommitSink:
    """커밋 후 항목을 받을 sink를 설정하고 이전 sink를 반환 (None이면 버림)"""
    global _after_commit_sink
    previous = _after_commit_sink
    _after_commit_sink = sink or _discard
    return previous


@event.listens_for(Session, "after_commit")
def _send_after_commit(session: Session) -> None:
    # SAVEPOINT RELEASE에도 after_commit이 온다. 루트 커밋에서만 내보낸다
    if session.in_nested_transaction():
        return
    items = session.info.pop(_AFTER_COMMIT_KEY, None)
    for _, item in items or ():
        try:
            _after_commit_sink(item)
        except Exception:
            logger.exception("after_commit_sink_failed")


@event.listens_for(Session, "after_transaction_end")
def _drop_after_commit(session: Session, transaction) -> None:
    # 루트 트랜잭션이 끝나면(커밋 후 남은 것, rollback, close) 비운다
    if transaction.parent is None:
        session.info.pop(_AFTER_COMMIT_KEY, None)
