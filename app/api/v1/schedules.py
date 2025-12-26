"""
Schedule Router

FastAPI Best Practices:
- 모든 라우트는 async
- Dependencies를 활용한 검증
- Service는 session을 받아서 CRUD 직접 사용
"""
from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from app.api.dependencies import get_db_transactional
from app.api.v1.schedules_dependencies import valid_schedule_id
from app.domain.schedule.model import Schedule
from app.domain.schedule.schema.dto import (
    ScheduleCreate,
    ScheduleRead,
    ScheduleUpdate,
)
from app.domain.schedule.service import ScheduleService

router = APIRouter(prefix="/schedules", tags=["Schedules"])


@router.post("", response_model=ScheduleRead, status_code=status.HTTP_201_CREATED)
async def create_schedule(
        data: ScheduleCreate,
        session: Session = Depends(get_db_transactional),
):
    """
    새 일정 생성
    
    FastAPI Best Practices:
    - async 라우트 사용
    - 트랜잭션 자동 관리 (context manager)
    - Exception Handler가 예외 처리
    """
    service = ScheduleService(session)
    return service.create_schedule(data)


@router.get("", response_model=list[ScheduleRead])
async def read_schedules(session: Session = Depends(get_db_transactional)):
    """
    모든 일정 조회
    
    FastAPI Best Practices:
    - async 라우트 사용
    """
    service = ScheduleService(session)
    return service.get_all_schedules()


@router.get("/{schedule_id}", response_model=ScheduleRead)
async def read_schedule(
        schedule: Schedule = Depends(valid_schedule_id),
):
    """
    ID로 일정 조회
    
    FastAPI Best Practices:
    - Dependency로 검증 (valid_schedule_id)
    - 중복 검증 코드 제거
    - 여러 엔드포인트에서 재사용 가능
    """
    return schedule


@router.patch("/{schedule_id}", response_model=ScheduleRead)
async def update_schedule(
        data: ScheduleUpdate,
        schedule: Schedule = Depends(valid_schedule_id),
        session: Session = Depends(get_db_transactional),
):
    """
    일정 업데이트
    
    FastAPI Best Practices:
    - Dependency로 schedule 검증 (valid_schedule_id)
    - Service는 session을 받아서 CRUD 직접 사용
    """
    service = ScheduleService(session)
    return service.update_schedule(schedule.id, data)


@router.delete("/{schedule_id}", status_code=status.HTTP_200_OK)
async def delete_schedule(
        schedule: Schedule = Depends(valid_schedule_id),
        session: Session = Depends(get_db_transactional),
):
    """
    일정 삭제
    
    FastAPI Best Practices:
    - Dependency로 schedule 검증 (valid_schedule_id)
    - Service는 session을 받아서 CRUD 직접 사용
    """
    service = ScheduleService(session)
    service.delete_schedule(schedule.id)
    return {"ok": True}
