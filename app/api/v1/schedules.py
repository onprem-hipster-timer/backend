"""
Schedule Router

FastAPI Best Practices:
- 모든 라우트는 async
- Dependencies를 활용한 검증
- Service는 session을 받아서 CRUD 직접 사용
"""
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session

from app.core.auth import CurrentUser, get_current_user
from app.db.session import get_db_transactional
from app.domain.dateutil.service import parse_timezone
from app.domain.schedule.schema.dto import (
    ScheduleCreate,
    ScheduleRead,
    ScheduleUpdate,
)
from app.domain.schedule.service import ScheduleService
from app.domain.timer.schema.dto import TimerRead
from app.domain.timer.service import TimerService

router = APIRouter(prefix="/schedules", tags=["Schedules"])


@router.post("", response_model=ScheduleRead, status_code=status.HTTP_201_CREATED)
async def create_schedule(
        data: ScheduleCreate,
        tz: Optional[str] = Query(
            None,
            alias="timezone",
            description="타임존 (예: UTC, +09:00, Asia/Seoul). 지정하지 않으면 UTC로 반환"
        ),
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    새 일정 생성
    
    FastAPI Best Practices:
    - async 라우트 사용
    - 트랜잭션 자동 관리 (context manager)
    - Exception Handler가 예외 처리
    """
    service = ScheduleService(session, current_user)
    schedule = service.create_schedule(data)

    # Schedule 모델을 ScheduleRead로 변환
    schedule_read = ScheduleRead.model_validate(schedule)

    # 타임존 변환
    tz_obj = parse_timezone(tz) if tz else None
    return schedule_read.to_timezone(tz_obj)


@router.get("", response_model=list[ScheduleRead])
async def read_schedules(
        start_date: datetime = Query(
            ...,
            description="조회 시작 날짜/시간 (ISO 8601 형식)"
        ),
        end_date: datetime = Query(
            ...,
            description="조회 종료 날짜/시간 (ISO 8601 형식)"
        ),
        tag_ids: Optional[List[UUID]] = Query(
            None,
            description="태그 ID 리스트 (AND 방식: 모든 지정 태그를 포함한 일정만 반환)"
        ),
        group_ids: Optional[List[UUID]] = Query(
            None,
            description="태그 그룹 ID 리스트 (해당 그룹의 태그를 가진 일정 반환)"
        ),
        tz: Optional[str] = Query(
            None,
            alias="timezone",
            description="타임존 (예: UTC, +09:00, Asia/Seoul). 지정하지 않으면 UTC로 반환"
        ),
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    날짜 범위 기반 일정 조회 (반복 일정 포함, 태그 필터링 지원)
    
    날짜 범위:
    - start_date: 조회 시작 날짜/시간 (필수)
    - end_date: 조회 종료 날짜/시간 (필수)
    - 지정된 날짜 범위와 겹치는 모든 일정을 반환 (반복 일정은 가상 인스턴스로 확장)
    
    태그 필터링:
    - tag_ids: AND 방식 (모든 지정 태그를 포함한 일정만 반환)
    - group_ids: 해당 그룹의 태그 중 하나라도 있는 일정 반환
    - 둘 다 지정 시: 그룹 필터링 후 태그 필터링 적용
    
    FastAPI Best Practices:
    - async 라우트 사용
    """
    service = ScheduleService(session, current_user)

    # 날짜 범위 기반 조회 (태그 필터링 포함)
    schedules = service.get_schedules_by_date_range(
        start_date=start_date,
        end_date=end_date,
        tag_ids=tag_ids,
        group_ids=group_ids,
    )

    tz_obj = parse_timezone(tz) if tz else None
    return [
        ScheduleRead.model_validate(schedule).to_timezone(tz_obj)
        for schedule in schedules
    ]


@router.get("/{schedule_id}", response_model=ScheduleRead)
async def read_schedule(
        schedule_id: UUID,
        tz: Optional[str] = Query(
            None,
            alias="timezone",
            description="타임존 (예: UTC, +09:00, Asia/Seoul). 지정하지 않으면 UTC로 반환"
        ),
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    ID로 일정 조회
    
    FastAPI Best Practices:
    - 인증된 사용자만 자신의 일정 조회 가능
    """
    service = ScheduleService(session, current_user)
    schedule = service.get_schedule(schedule_id)

    # Schedule 모델을 ScheduleRead로 변환
    schedule_read = ScheduleRead.model_validate(schedule)

    # 타임존 변환
    tz_obj = parse_timezone(tz) if tz else None
    return schedule_read.to_timezone(tz_obj)


@router.patch("/{schedule_id}", response_model=ScheduleRead)
async def update_schedule(
        schedule_id: UUID,
        data: ScheduleUpdate,
        instance_start: datetime | None = Query(None, description="반복 일정 인스턴스 시작 시간 (ISO 8601 형식)"),
        tz: Optional[str] = Query(
            None,
            alias="timezone",
            description="타임존 (예: UTC, +09:00, Asia/Seoul). 지정하지 않으면 UTC로 반환"
        ),
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    일정 업데이트 (반복 일정 인스턴스 포함)
    
    일반 일정과 가상 인스턴스 모두 지원:
    - 일반 일정: schedule_id로 조회하여 업데이트
    - 가상 인스턴스: schedule_id를 parent_id로 사용하고 instance_start를 쿼리 파라미터로 전송
    
    ### 요청 예시
    ```json
    {
        "title": "업데이트된 제목"
    }
    ```
    
    FastAPI Best Practices:
    - Service는 session을 받아서 CRUD 직접 사용
    - 가상 인스턴스인 경우 instance_start 쿼리 파라미터로 처리
    """
    service = ScheduleService(session, current_user)
    if instance_start:
        schedule = service.update_recurring_instance(schedule_id, instance_start, data)
    else:
        schedule = service.update_schedule(schedule_id, data)

    # Schedule 모델을 ScheduleRead로 변환
    schedule_read = ScheduleRead.model_validate(schedule)

    # 타임존 변환
    tz_obj = parse_timezone(tz) if tz else None
    return schedule_read.to_timezone(tz_obj)


@router.delete("/{schedule_id}", status_code=status.HTTP_200_OK)
async def delete_schedule(
        schedule_id: UUID,
        instance_start: datetime | None = Query(None, description="반복 일정 인스턴스 시작 시간 (ISO 8601 형식)"),
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
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
    service = ScheduleService(session, current_user)
    if instance_start:
        service.delete_recurring_instance(schedule_id, instance_start)
    else:
        service.delete_schedule(schedule_id)

    return {"ok": True}


@router.get("/{schedule_id}/timers", response_model=list[TimerRead])
async def get_schedule_timers(
        schedule_id: UUID,
        include_schedule: bool = Query(
            False,
            description="Schedule 정보 포함 여부 (기본값: false)"
        ),
        tz: Optional[str] = Query(
            None,
            alias="timezone",
            description="타임존 (예: UTC, +09:00, Asia/Seoul). 지정하지 않으면 UTC로 반환"
        ),
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    일정의 모든 타이머 조회
    """
    from app.domain.schedule.schema.dto import ScheduleRead
    from app.domain.timer.schema.dto import TimerRead

    schedule_service = ScheduleService(session, current_user)
    schedule = schedule_service.get_schedule(schedule_id)

    timer_service = TimerService(session, current_user)
    timers = timer_service.get_timers_by_schedule(schedule.id)

    # Schedule 정보 처리
    schedule_read = None
    if include_schedule:
        schedule_read = ScheduleRead.model_validate(schedule)

    tz_obj = parse_timezone(tz) if tz else None
    return [
        TimerRead.from_model(
            timer,
            include_schedule=include_schedule,
            schedule=schedule_read,
        ).to_timezone(tz_obj, validate=False)
        for timer in timers
    ]


@router.get("/{schedule_id}/timers/active", response_model=TimerRead)
async def get_active_timer(
        schedule_id: UUID,
        include_schedule: bool = Query(
            False,
            description="Schedule 정보 포함 여부 (기본값: false)"
        ),
        tz: Optional[str] = Query(
            None,
            alias="timezone",
            description="타임존 (예: UTC, +09:00, Asia/Seoul). 지정하지 않으면 UTC로 반환"
        ),
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    일정의 현재 활성 타이머 조회 (RUNNING 또는 PAUSED)
    
    활성 타이머가 없으면 404를 반환합니다.
    """
    from app.domain.timer.exceptions import TimerNotFoundError
    from app.domain.schedule.schema.dto import ScheduleRead
    from app.domain.timer.schema.dto import TimerRead

    schedule_service = ScheduleService(session, current_user)
    schedule = schedule_service.get_schedule(schedule_id)

    timer_service = TimerService(session, current_user)
    timer = timer_service.get_active_timer(schedule.id)
    if not timer:
        raise TimerNotFoundError()

    # Schedule 정보 처리
    schedule_read = None
    if include_schedule:
        schedule_read = ScheduleRead.model_validate(schedule)

    # Timer 모델을 TimerRead로 변환 (안전한 변환 - 관계 필드 제외)
    timer_read = TimerRead.from_model(
        timer,
        include_schedule=include_schedule,
        schedule=schedule_read,
    )

    # 타임존 변환 (from_model로 이미 검증된 인스턴스이므로 validate=False)
    tz_obj = parse_timezone(tz) if tz else None
    return timer_read.to_timezone(tz_obj, validate=False)


@router.post("/{schedule_id}/todo", status_code=status.HTTP_201_CREATED)
async def create_todo_from_schedule(
        schedule_id: UUID,
        tag_group_id: UUID = Query(
            ...,
            description="Todo가 속할 TagGroup ID (필수)"
        ),
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    기존 Schedule에서 연관된 Todo 생성
    
    Schedule의 정보를 기반으로 새로운 Todo를 생성합니다:
    - Todo의 title, description은 Schedule에서 복사
    - Todo의 deadline은 Schedule의 start_time으로 설정
    - Schedule의 태그가 Todo에도 복사됨
    - 생성된 Todo와 Schedule이 source_todo_id로 연결됨
    
    제약사항:
    - 이미 Todo와 연결된 Schedule에서는 호출 불가 (400 에러)
    - tag_group_id는 필수 파라미터
    
    :param schedule_id: Schedule ID
    :param tag_group_id: Todo가 속할 TagGroup ID
    :return: 생성된 Todo
    """
    from app.domain.todo.service import TodoService

    schedule_service = ScheduleService(session, current_user)
    todo = schedule_service.create_todo_from_schedule(schedule_id, tag_group_id)

    # TodoService를 사용하여 TodoRead DTO로 변환
    todo_service = TodoService(session, current_user)
    return todo_service.to_read_dto(todo)
