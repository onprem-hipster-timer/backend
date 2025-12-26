from datetime import datetime

from sqlmodel import Session, select

from app.domain.schedule.schema.dto import ScheduleCreate, ScheduleUpdate
from app.models.schedule import Schedule


def create_schedule(session: Session, data: ScheduleCreate) -> Schedule:
    """
    새 Schedule을 DB에 생성합니다.
    
    FastAPI Best Practices:
    - commit은 get_db_transactional이 처리
    - CRUD는 데이터 접근만 담당
    """
    schedule = Schedule.model_validate(data)
    session.add(schedule)
    # commit은 get_db_transactional이 처리
    session.flush()  # ID를 얻기 위해 flush
    session.refresh(schedule)
    return schedule


def get_schedules(session: Session) -> list[Schedule]:
    """
    모든 Schedule 객체를 조회합니다.
    """
    statement = select(Schedule)
    results = session.exec(statement)
    return results.all()


def get_schedules_by_date_range(
        session: Session,
        start_date: datetime,
        end_date: datetime,
) -> list[Schedule]:
    """
    날짜 범위로 Schedule 객체를 조회합니다.
    
    :param session: DB 세션
    :param start_date: 시작 날짜 (이 날짜 이후에 시작하는 일정 포함)
    :param end_date: 종료 날짜 (이 날짜 이전에 종료하는 일정 포함)
    :return: 해당 날짜 범위와 겹치는 모든 일정
    """
    # 일정이 주어진 날짜 범위와 겹치는 경우를 조회
    # 일정의 start_time <= end_date AND 일정의 end_time >= start_date
    statement = (
        select(Schedule)
        .where(Schedule.start_time <= end_date)
        .where(Schedule.end_time >= start_date)
        .order_by(Schedule.start_time)
    )
    results = session.exec(statement)
    return results.all()


def get_schedule(session: Session, schedule_id) -> Schedule | None:
    """
    ID로 Schedule 조회 (없으면 None 반환)
    """
    return session.get(Schedule, schedule_id)


def update_schedule(
        session: Session,
        schedule: Schedule,
        data: ScheduleUpdate
) -> Schedule:
    """
    Schedule 객체의 변경된 필드만 반영해 업데이트합니다.
    
    FastAPI Best Practices:
    - commit은 get_db_transactional이 처리
    - exclude_none=True: None 값은 업데이트하지 않음 (기존 값 유지)
    """
    update_data = data.model_dump(exclude_unset=True, exclude_none=True)
    for field, value in update_data.items():
        setattr(schedule, field, value)

    # commit은 get_db_transactional이 처리
    session.flush()
    session.refresh(schedule)
    return schedule


def delete_schedule(session: Session, schedule: Schedule) -> None:
    """
    Schedule 객체를 삭제합니다.
    
    FastAPI Best Practices:
    - commit은 get_db_transactional이 처리
    - flush를 호출하여 즉시 DB에 반영
    """
    session.delete(schedule)
    # flush를 호출하여 즉시 DB에 반영 (commit은 get_db_transactional이 처리)
    session.flush()
