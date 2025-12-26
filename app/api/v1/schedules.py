from fastapi import APIRouter, Depends, status
from sqlmodel import Session
from uuid import UUID

from app.api.dependencies import get_db_transactional
from app.schemas.schedule import (
    ScheduleCreate,
    ScheduleRead,
    ScheduleUpdate,
)
from app.crud import schedule as crud
from app.core.error_handlers import DomainException


class ScheduleNotFoundError(DomainException):
    """일정을 찾을 수 없음"""
    status_code = 404
    detail = "Schedule not found"


router = APIRouter(prefix="/schedules", tags=["Schedules"])


@router.post("", response_model=ScheduleRead, status_code=status.HTTP_201_CREATED)
def create_schedule(
    data: ScheduleCreate,
    session: Session = Depends(get_db_transactional),
):
    """
    새 일정 생성
    
    ✅ 트랜잭션 자동 관리:
    - try/except 필요 없음
    - Exception Handler가 예외 처리
    - session.commit() 불필요 (context manager가 처리)
    """
    return crud.create_schedule(session, data)


@router.get("", response_model=list[ScheduleRead])
def read_schedules(session: Session = Depends(get_db_transactional)):
    """모든 일정 조회"""
    return crud.get_schedules(session)


@router.get("/{schedule_id}", response_model=ScheduleRead)
def read_schedule(
    schedule_id: UUID,
    session: Session = Depends(get_db_transactional),
):
    """ID로 일정 조회"""
    schedule = crud.get_schedule(session, schedule_id)
    if not schedule:
        raise ScheduleNotFoundError()
    return schedule


@router.patch("/{schedule_id}", response_model=ScheduleRead)
def update_schedule(
    schedule_id: UUID,
    data: ScheduleUpdate,
    session: Session = Depends(get_db_transactional),
):
    """일정 업데이트"""
    schedule = crud.get_schedule(session, schedule_id)
    if not schedule:
        raise ScheduleNotFoundError()
    return crud.update_schedule(session, schedule, data)


@router.delete("/{schedule_id}", status_code=status.HTTP_200_OK)
def delete_schedule(
    schedule_id: UUID,
    session: Session = Depends(get_db_transactional),
):
    """일정 삭제"""
    schedule = crud.get_schedule(session, schedule_id)
    if not schedule:
        raise ScheduleNotFoundError()
    crud.delete_schedule(session, schedule)
    return {"ok": True}

