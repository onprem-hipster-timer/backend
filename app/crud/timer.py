from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlmodel import Session, select, and_

from app.core.constants import TimerStatus
from app.models.timer import TimerSession


def create_timer(session: Session, timer_data: dict, owner_id: str) -> TimerSession:
    """
    새 TimerSession을 DB에 생성합니다.
    
    FastAPI Best Practices:
    - commit은 get_db_transactional이 처리
    - CRUD는 데이터 접근만 담당
    
    :param session: DB 세션
    :param timer_data: 타이머 데이터
    :param owner_id: 소유자 ID (OIDC sub claim)
    """
    timer_data['owner_id'] = owner_id
    timer = TimerSession(**timer_data)
    session.add(timer)
    session.flush()  # ID를 얻기 위해 flush
    session.refresh(timer)
    return timer


def get_timer(session: Session, timer_id: UUID, owner_id: str) -> TimerSession | None:
    """
    ID로 TimerSession 조회 (owner_id 검증 포함)
    """
    statement = (
        select(TimerSession)
        .where(TimerSession.id == timer_id)
        .where(TimerSession.owner_id == owner_id)
    )
    return session.exec(statement).first()


def get_timer_by_id(session: Session, timer_id: UUID) -> TimerSession | None:
    """
    ID로 TimerSession 조회 (소유자 검증 없음 - 접근 제어는 Service에서 처리)
    
    공유 리소스 접근 시 사용
    """
    return session.get(TimerSession, timer_id)


def get_timers_by_ids(session: Session, timer_ids: list[UUID]) -> list[TimerSession]:
    """
    여러 ID로 TimerSession 배치 조회 (소유자 검증 없음)
    
    공유 리소스 조회 시 N+1 문제 방지를 위해 사용
    
    :param session: DB 세션
    :param timer_ids: 조회할 Timer ID 목록
    :return: TimerSession 리스트
    """
    if not timer_ids:
        return []
    statement = select(TimerSession).where(TimerSession.id.in_(timer_ids))
    return list(session.exec(statement).all())


def get_timers_by_schedule(
        session: Session,
        schedule_id: UUID,
        owner_id: str,
) -> list[TimerSession]:
    """
    일정의 모든 타이머 조회
    
    :param session: DB 세션
    :param schedule_id: 일정 ID
    :param owner_id: 소유자 ID
    :return: 타이머 리스트
    """
    statement = (
        select(TimerSession)
        .where(TimerSession.owner_id == owner_id)
        .where(TimerSession.schedule_id == schedule_id)
        .order_by(TimerSession.created_at.desc())
    )

    results = session.exec(statement)
    return results.all()


def get_active_timer(
        session: Session,
        schedule_id: UUID,
        owner_id: str,
) -> TimerSession | None:
    """
    일정의 현재 활성 타이머 조회 (RUNNING 또는 PAUSED)
    
    :param session: DB 세션
    :param schedule_id: 일정 ID
    :param owner_id: 소유자 ID
    :return: 활성 타이머 또는 None
    """
    statement = (
        select(TimerSession)
        .where(TimerSession.owner_id == owner_id)
        .where(TimerSession.schedule_id == schedule_id)
        .where(
            TimerSession.status.in_([
                TimerStatus.RUNNING.value,
                TimerStatus.PAUSED.value,
            ])
        )
        .order_by(TimerSession.created_at.desc())
        .limit(1)
    )

    return session.exec(statement).first()


def get_timers_by_todo(
        session: Session,
        todo_id: UUID,
        owner_id: str,
) -> list[TimerSession]:
    """
    Todo의 모든 타이머 조회
    
    :param session: DB 세션
    :param todo_id: Todo ID
    :param owner_id: 소유자 ID
    :return: 타이머 리스트
    """
    statement = (
        select(TimerSession)
        .where(TimerSession.owner_id == owner_id)
        .where(TimerSession.todo_id == todo_id)
        .order_by(TimerSession.created_at.desc())
    )

    results = session.exec(statement)
    return results.all()


def get_active_timer_by_todo(
        session: Session,
        todo_id: UUID,
        owner_id: str,
) -> TimerSession | None:
    """
    Todo의 현재 활성 타이머 조회 (RUNNING 또는 PAUSED)
    
    :param session: DB 세션
    :param todo_id: Todo ID
    :param owner_id: 소유자 ID
    :return: 활성 타이머 또는 None
    """
    statement = (
        select(TimerSession)
        .where(TimerSession.owner_id == owner_id)
        .where(TimerSession.todo_id == todo_id)
        .where(
            TimerSession.status.in_([
                TimerStatus.RUNNING.value,
                TimerStatus.PAUSED.value,
            ])
        )
        .order_by(TimerSession.created_at.desc())
        .limit(1)
    )

    return session.exec(statement).first()


def delete_timer(session: Session, timer: TimerSession) -> None:
    """
    TimerSession 객체를 삭제합니다.
    
    FastAPI Best Practices:
    - commit은 get_db_transactional이 처리
    """
    session.delete(timer)
    # commit은 get_db_transactional이 처리


def get_all_timers(
        session: Session,
        owner_id: str,
        status: Optional[list[str]] = None,
        timer_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
) -> list[TimerSession]:
    """
    사용자의 모든 타이머 조회 (필터링 옵션 지원)
    
    :param session: DB 세션
    :param owner_id: 소유자 ID
    :param status: 상태 필터 리스트 (RUNNING, PAUSED, COMPLETED, CANCELLED)
    :param timer_type: 타입 필터 (independent, schedule, todo)
    :param start_date: 시작 날짜 필터 (started_at 기준)
    :param end_date: 종료 날짜 필터 (started_at 기준)
    :return: 타이머 리스트
    """
    statement = (
        select(TimerSession)
        .where(TimerSession.owner_id == owner_id)
    )

    # 상태 필터
    if status:
        statement = statement.where(TimerSession.status.in_(status))

    # 타입 필터
    if timer_type == "independent":
        # 독립 타이머: schedule_id와 todo_id 모두 null
        statement = statement.where(
            and_(
                TimerSession.schedule_id.is_(None),
                TimerSession.todo_id.is_(None)
            )
        )
    elif timer_type == "schedule":
        # Schedule 연결 타이머
        statement = statement.where(TimerSession.schedule_id.is_not(None))
    elif timer_type == "todo":
        # Todo 연결 타이머
        statement = statement.where(TimerSession.todo_id.is_not(None))

    # 날짜 범위 필터 (started_at 기준)
    if start_date:
        statement = statement.where(TimerSession.started_at >= start_date)
    if end_date:
        statement = statement.where(TimerSession.started_at <= end_date)

    # 최신순 정렬
    statement = statement.order_by(TimerSession.created_at.desc())

    results = session.exec(statement)
    return results.all()


def get_user_active_timer(
        session: Session,
        owner_id: str,
) -> TimerSession | None:
    """
    사용자의 현재 활성 타이머 조회 (RUNNING 또는 PAUSED)
    
    여러 개가 있으면 가장 최근 것 반환
    
    :param session: DB 세션
    :param owner_id: 소유자 ID
    :return: 활성 타이머 또는 None
    """
    statement = (
        select(TimerSession)
        .where(TimerSession.owner_id == owner_id)
        .where(
            TimerSession.status.in_([
                TimerStatus.RUNNING.value,
                TimerStatus.PAUSED.value,
            ])
        )
        .order_by(TimerSession.created_at.desc())
        .limit(1)
    )

    return session.exec(statement).first()
