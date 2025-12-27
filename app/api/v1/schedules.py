"""
Schedule Router

FastAPI Best Practices:
- 모든 라우트는 async
- Dependencies를 활용한 검증
- Service는 session을 받아서 CRUD 직접 사용
"""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session

from app.db.session import get_db_transactional
from app.domain.schedule.dependencies import valid_schedule_id
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
        schedule_id: UUID,
        data: ScheduleUpdate,
        instance_start: datetime | None = Query(None, description="반복 일정 인스턴스 시작 시간 (ISO 8601 형식)"),
        session: Session = Depends(get_db_transactional),
):
    """
    일정 업데이트 (반복 일정 인스턴스 포함)
    
    일반 일정과 가상 인스턴스 모두 지원:
    - 일반 일정: schedule_id로 조회하여 업데이트
    - 가상 인스턴스: schedule_id를 parent_id로 사용하고 instance_start를 쿼리 파라미터로 전송
    
    FastAPI Best Practices:
    - Service는 session을 받아서 CRUD 직접 사용
    - 가상 인스턴스인 경우 instance_start 쿼리 파라미터로 처리
    """
    service = ScheduleService(session)
    if instance_start:
        return service.update_recurring_instance(schedule_id, instance_start, data)
    else:
        return service.update_schedule(schedule_id, data)


@router.delete("/{schedule_id}", status_code=status.HTTP_200_OK)
async def delete_schedule(
        schedule_id: UUID,
        instance_start: datetime | None = Query(None, description="반복 일정 인스턴스 시작 시간 (ISO 8601 형식)"),
        session: Session = Depends(get_db_transactional),
):
    """
    일정 삭제 (반복 일정 인스턴스 포함)
    
    일반 일정과 가상 인스턴스 모두 지원:
    - 일반 일정: schedule_id로 조회하여 삭제
    - 가상 인스턴스: schedule_id를 parent_id로 사용하고 instance_start를 쿼리 파라미터로 전송
    
    FastAPI Best Practices:
    - Service는 session을 받아서 CRUD 직접 사용
    - 가상 인스턴스인 경우 instance_start 쿼리 파라미터로 처리
    """
    service = ScheduleService(session)
    if instance_start:
        service.delete_recurring_instance(schedule_id, instance_start)
    else:
        service.delete_schedule(schedule_id)
    
    return {"ok": True}
