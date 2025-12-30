"""
Timer Router

FastAPI Best Practices:
- 모든 라우트는 async
- Dependencies를 활용한 검증
- Service는 session을 받아서 CRUD 직접 사용
"""
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session

from app.db.session import get_db_transactional
from app.domain.dateutil.service import convert_utc_naive_to_timezone, parse_timezone
from app.domain.timer.dependencies import valid_timer_id
from app.domain.timer.model import TimerSession
from app.domain.timer.schema.dto import (
    TimerCreate,
    TimerRead,
    TimerUpdate,
)
from app.domain.timer.service import TimerService

router = APIRouter(prefix="/timers", tags=["Timers"])


def timer_to_dto(
        timer: TimerSession,
        session: Session,
        tz: Optional[timezone] = None
) -> TimerRead:
    """
    TimerSession을 TimerRead DTO로 변환 (Schedule 정보 포함)
    
    :param timer: TimerSession 인스턴스
    :param session: DB 세션
    :param tz: 타임존 변환 옵션 (None이면 UTC로 반환)
    :return: TimerRead DTO
    """
    from app.domain.schedule.service import ScheduleService
    from app.domain.schedule.schema.dto import ScheduleRead

    schedule_service = ScheduleService(session)
    schedule = schedule_service.get_schedule(timer.schedule_id)

    timer_dict = timer.model_dump()

    # 타임존 변환 (지정된 경우): UTC naive → 지정된 타임존 aware
    if tz:
        for field in ["started_at", "paused_at", "ended_at", "created_at", "updated_at"]:
            if timer_dict.get(field) is not None:
                dt = timer_dict[field]
                if isinstance(dt, datetime):
                    timer_dict[field] = convert_utc_naive_to_timezone(dt, tz)

    # Schedule SQLModel 인스턴스를 dict로 변환한 후 ScheduleRead로 변환
    schedule_dict = schedule.model_dump()

    # Schedule의 datetime 필드도 타임존 변환
    if tz:
        for field in ["start_time", "end_time", "recurrence_end", "created_at"]:
            if schedule_dict.get(field) is not None:
                dt = schedule_dict[field]
                if isinstance(dt, datetime):
                    schedule_dict[field] = convert_utc_naive_to_timezone(dt, tz)

    timer_dict["schedule"] = ScheduleRead.model_validate(schedule_dict).model_dump()

    return TimerRead(**timer_dict)


@router.post("", response_model=TimerRead, status_code=status.HTTP_201_CREATED)
async def create_timer(
        data: TimerCreate,
        tz: Optional[str] = Query(
            None,
            alias="timezone",
            description="타임존 (예: UTC, +09:00, Asia/Seoul). 지정하지 않으면 UTC로 반환"
        ),
        session: Session = Depends(get_db_transactional),
):
    """
    새 타이머 생성 및 시작
    
    FastAPI Best Practices:
    - async 라우트 사용
    - 트랜잭션 자동 관리 (context manager)
    - Exception Handler가 예외 처리
    """
    service = TimerService(session)
    timer = service.create_timer(data)

    tz_obj = parse_timezone(tz) if tz else None
    return timer_to_dto(timer, session, tz_obj)


@router.get("/{timer_id}", response_model=TimerRead)
async def get_timer(
        timer: TimerSession = Depends(valid_timer_id),
        tz: Optional[str] = Query(
            None,
            alias="timezone",
            description="타임존 (예: UTC, +09:00, Asia/Seoul). 지정하지 않으면 UTC로 반환"
        ),
        session: Session = Depends(get_db_transactional),
):
    """
    타이머 조회 (Schedule 정보 포함)
    
    FastAPI Best Practices:
    - Dependency로 검증 (valid_timer_id)
    """
    service = TimerService(session)
    timer = service.get_timer(timer.id)

    tz_obj = parse_timezone(tz) if tz else None
    return timer_to_dto(timer, session, tz_obj)


@router.patch("/{timer_id}", response_model=TimerRead)
async def update_timer(
        timer_id: UUID,
        data: TimerUpdate,
        tz: Optional[str] = Query(
            None,
            alias="timezone",
            description="타임존 (예: UTC, +09:00, Asia/Seoul). 지정하지 않으면 UTC로 반환"
        ),
        session: Session = Depends(get_db_transactional),
):
    """
    타이머 메타데이터 업데이트 (title, description)
    """
    service = TimerService(session)
    timer = service.update_timer(timer_id, data)

    tz_obj = parse_timezone(tz) if tz else None
    return timer_to_dto(timer, session, tz_obj)


@router.patch("/{timer_id}/pause", response_model=TimerRead)
async def pause_timer(
        timer_id: UUID,
        tz: Optional[str] = Query(
            None,
            alias="timezone",
            description="타임존 (예: UTC, +09:00, Asia/Seoul). 지정하지 않으면 UTC로 반환"
        ),
        session: Session = Depends(get_db_transactional),
):
    """
    타이머 일시정지
    """
    service = TimerService(session)
    timer = service.pause_timer(timer_id)

    tz_obj = parse_timezone(tz) if tz else None
    return timer_to_dto(timer, session, tz_obj)


@router.patch("/{timer_id}/resume", response_model=TimerRead)
async def resume_timer(
        timer_id: UUID,
        tz: Optional[str] = Query(
            None,
            alias="timezone",
            description="타임존 (예: UTC, +09:00, Asia/Seoul). 지정하지 않으면 UTC로 반환"
        ),
        session: Session = Depends(get_db_transactional),
):
    """
    타이머 재개
    """
    service = TimerService(session)
    timer = service.resume_timer(timer_id)

    tz_obj = parse_timezone(tz) if tz else None
    return timer_to_dto(timer, session, tz_obj)


@router.post("/{timer_id}/stop", response_model=TimerRead)
async def stop_timer(
        timer_id: UUID,
        tz: Optional[str] = Query(
            None,
            alias="timezone",
            description="타임존 (예: UTC, +09:00, Asia/Seoul). 지정하지 않으면 UTC로 반환"
        ),
        session: Session = Depends(get_db_transactional),
):
    """
    타이머 종료
    """
    service = TimerService(session)
    timer = service.stop_timer(timer_id)

    tz_obj = parse_timezone(tz) if tz else None
    return timer_to_dto(timer, session, tz_obj)


@router.delete("/{timer_id}", status_code=status.HTTP_200_OK)
async def delete_timer(
        timer_id: UUID,
        session: Session = Depends(get_db_transactional),
):
    """
    타이머 삭제
    """
    service = TimerService(session)
    service.delete_timer(timer_id)
    return {"ok": True}
