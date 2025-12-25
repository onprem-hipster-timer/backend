from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from app.db.session import get_session
from app.schemas.schedule import (
    ScheduleCreate,
    ScheduleRead,
    ScheduleUpdate,
)
from app.crud import schedule as crud

router = APIRouter(prefix="/schedules", tags=["Schedules"])

@router.post("", response_model=ScheduleRead)
def create_schedule(
    data: ScheduleCreate,
    session: Session = Depends(get_session),
):
    return crud.create_schedule(session, data)

@router.get("", response_model=list[ScheduleRead])
def read_schedules(session: Session = Depends(get_session)):
    return crud.get_schedules(session)

@router.get("/{schedule_id}", response_model=ScheduleRead)
def read_schedule(
    schedule_id: int,
    session: Session = Depends(get_session),
):
    schedule = crud.get_schedule(session, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return schedule

@router.patch("/{schedule_id}", response_model=ScheduleRead)
def update_schedule(
    schedule_id: int,
    data: ScheduleUpdate,
    session: Session = Depends(get_session),
):
    schedule = crud.get_schedule(session, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return crud.update_schedule(session, schedule, data)

@router.delete("/{schedule_id}")
def delete_schedule(
    schedule_id: int,
    session: Session = Depends(get_session),
):
    schedule = crud.get_schedule(session, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    crud.delete_schedule(session, schedule)
    return {"ok": True}
