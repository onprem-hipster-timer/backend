"""
세션 스코프 이벤트 수집 helper (#54)

도메인 모델이 SQLModel ORM 클래스의 alias라 엔티티에 `.events` 리스트를
직접 붙일 수 없어, 1차 구현은 `session.info` 기반 세션 스코프 수집을 사용합니다.

!!! important
    `session.info`는 트랜잭션 aware가 아닙니다 — DB rollback이 돼도 이벤트
    큐가 자동으로 비워지지 않습니다. rollback 경계에서 반드시
    `clear_events(session)`를 호출해야 합니다 (doc §4.2).

이 모듈의 helper로만 큐에 접근합니다 (`session.info` 직접 접근 금지).
"""
from typing import TYPE_CHECKING, List

from sqlmodel import Session

if TYPE_CHECKING:
    from app.shared.events import DomainEvent

_EVENTS_KEY = "domain_events"


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

    쓰기 use-case가 응답 DTO를 조립하기 전에 호출해, 핸들러가 만든
    자동 생성 리소스가 응답에 즉시 보이게 합니다 (doc §2).
    핸들러 예외는 전파됩니다 → 호출자(트랜잭션 경계)에서 전체 rollback.
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
