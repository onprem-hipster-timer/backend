from fastapi import APIRouter, Depends, status
from sqlmodel import Session
from uuid import UUID

from app.api.dependencies import get_db_transactional
from app.domain.schedule.schema.dto import (
    ScheduleCreate,
    ScheduleRead,
    ScheduleUpdate,
)
from app.domain.schedule.service import ScheduleService
from app.domain.schedule.repository import ScheduleRepository

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
    repository = ScheduleRepository(session)
    service = ScheduleService(repository)
    return service.create_schedule(data)


@router.get("", response_model=list[ScheduleRead])
def read_schedules(session: Session = Depends(get_db_transactional)):
    """모든 일정 조회"""
    repository = ScheduleRepository(session)
    service = ScheduleService(repository)
    return service.get_all_schedules()


@router.get("/{schedule_id}", response_model=ScheduleRead)
def read_schedule(
    schedule_id: UUID,
    session: Session = Depends(get_db_transactional),
):
    """ID로 일정 조회"""
    repository = ScheduleRepository(session)
    service = ScheduleService(repository)
    return service.get_schedule(schedule_id)


@router.patch("/{schedule_id}", response_model=ScheduleRead)
def update_schedule(
    schedule_id: UUID,
    data: ScheduleUpdate,
    session: Session = Depends(get_db_transactional),
):
    """일정 업데이트"""
    repository = ScheduleRepository(session)
    service = ScheduleService(repository)
    return service.update_schedule(schedule_id, data)


@router.delete("/{schedule_id}", status_code=status.HTTP_200_OK)
def delete_schedule(
    schedule_id: UUID,
    session: Session = Depends(get_db_transactional),
):
    """일정 삭제"""
    repository = ScheduleRepository(session)
    service = ScheduleService(repository)
    service.delete_schedule(schedule_id)
    return {"ok": True}

