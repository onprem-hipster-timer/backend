from uuid import UUID

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
    ID로 TimerSession 조회
    """
    statement = select(TimerSession).where(TimerSession.id == timer_id)
    return session.exec(statement).first()




def get_timers_by_schedule(
        session: Session,
        schedule_id: UUID,
) -> list[TimerSession]:
    """
    일정의 모든 타이머 조회
    
    :param session: DB 세션
    :param schedule_id: 일정 ID
    :return: 타이머 리스트
    """
    statement = (
        select(TimerSession)
        .where(TimerSession.schedule_id == schedule_id)
        .order_by(TimerSession.created_at.desc())
    )

    results = session.exec(statement)
    return results.all()


def get_active_timer(
        session: Session,
        schedule_id: UUID,
) -> TimerSession | None:
    """
    일정의 현재 활성 타이머 조회 (RUNNING 또는 PAUSED)
    
    :param session: DB 세션
    :param schedule_id: 일정 ID
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

    return session.exec(statement).first()


def delete_timer(session: Session, timer: TimerSession) -> None:
    """
    TimerSession 객체를 삭제합니다.
    
    FastAPI Best Practices:
    - commit은 get_db_transactional이 처리
    """
    session.delete(timer)
    # commit은 get_db_transactional이 처리
