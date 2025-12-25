from sqlmodel import Session, select
from app.models.schedule import Schedule
from app.schemas.schedule import ScheduleCreate, ScheduleUpdate

def create_schedule(session: Session, data: ScheduleCreate):
    schedule = Schedule.from_orm(data)
    session.add(schedule)
    session.commit()
    session.refresh(schedule)
    return schedule

def get_schedules(session: Session):
    return session.exec(select(Schedule)).all()

def get_schedule(session: Session, schedule_id: int):
    return session.get(Schedule, schedule_id)

def update_schedule(session: Session, schedule: Schedule, data: ScheduleUpdate):
    update_data = data.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(schedule, key, value)
    session.add(schedule)
    session.commit()
    session.refresh(schedule)
    return schedule

def delete_schedule(session: Session, schedule: Schedule):
    session.delete(schedule)
    session.commit()
