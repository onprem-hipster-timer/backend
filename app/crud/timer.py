from uuid import UUID

from sqlalchemy.orm import selectinload
from sqlmodel import Session, select

from app.core.constants import TimerStatus
from app.models.timer import TimerSession


def create_timer(session: Session, timer_data: dict) -> TimerSession:
    """
    새 TimerSession을 DB에 생성합니다.
    
    FastAPI Best Practices:
    - commit은 get_db_transactional이 처리
    - CRUD는 데이터 접근만 담당
    """
    timer = TimerSession(**timer_data)
    session.add(timer)
    session.flush()  # ID를 얻기 위해 flush
    session.refresh(timer)
    return timer


def get_timer(session: Session, timer_id: UUID) -> TimerSession | None:
    """
    ID로 TimerSession 조회 (없으면 None 반환)
    """
    return session.get(TimerSession, timer_id)


def get_timer_with_schedule(session: Session, timer_id: UUID) -> TimerSession | None:
    """
    ID로 TimerSession 조회 (Schedule relationship 포함)
    
    Relationship을 로딩하여 schedule 정보를 함께 가져옵니다.
    """
    statement = (
        select(TimerSession)
        .options(selectinload(TimerSession.schedule))
        .where(TimerSession.id == timer_id)
    )
    return session.exec(statement).first()


def get_timers_by_schedule(
        session: Session,
        schedule_id: UUID,
        include_schedule: bool = True,
) -> list[TimerSession]:
    """
    일정의 모든 타이머 조회
    
    :param session: DB 세션
    :param schedule_id: 일정 ID
    :param include_schedule: Schedule relationship 포함 여부
    :return: 타이머 리스트
    """
    statement = (
        select(TimerSession)
        .where(TimerSession.schedule_id == schedule_id)
        .order_by(TimerSession.created_at.desc())
    )

    if include_schedule:
        statement = statement.options(selectinload(TimerSession.schedule))

    results = session.exec(statement)
    return results.all()


def get_active_timer(
        session: Session,
        schedule_id: UUID,
        include_schedule: bool = True,
) -> TimerSession | None:
    """
    일정의 현재 활성 타이머 조회 (RUNNING 또는 PAUSED)
    
    :param session: DB 세션
    :param schedule_id: 일정 ID
    :param include_schedule: Schedule relationship 포함 여부
    :return: 활성 타이머 또는 None
    """
    statement = (
        select(TimerSession)
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

    if include_schedule:
        statement = statement.options(selectinload(TimerSession.schedule))

    return session.exec(statement).first()


def delete_timer(session: Session, timer: TimerSession) -> None:
    """
    TimerSession 객체를 삭제합니다.
    
    FastAPI Best Practices:
    - commit은 get_db_transactional이 처리
    """
    session.delete(timer)
    # commit은 get_db_transactional이 처리
