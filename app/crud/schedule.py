from sqlmodel import Session, select
from app.models.schedule import Schedule
from app.schemas.schedule import ScheduleCreate, ScheduleUpdate


def create_schedule(session: Session, data: ScheduleCreate) -> Schedule:
    """
    새 Schedule을 DB에 생성합니다.
    """
    # Pydantic 모델을 SQLModel 인스턴스로 변환
    schedule = Schedule.from_orm(data)

    session.add(schedule)
    session.commit()
    session.refresh(schedule)

    return schedule


def get_schedules(session: Session) -> list[Schedule]:
    """
    모든 Schedule 객체를 조회합니다.
    """
    statement = select(Schedule)
    results = session.exec(statement)
    return results.all()


def get_schedule(session: Session, schedule_id: int) -> Schedule | None:
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
    """
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(schedule, field, value)

    session.add(schedule)
    session.commit()
    session.refresh(schedule)

    return schedule


def delete_schedule(session: Session, schedule: Schedule) -> None:
    """
    Schedule 객체를 삭제합니다.
    """
    session.delete(schedule)
    session.commit()
