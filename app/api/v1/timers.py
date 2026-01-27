"""
Timer Router

FastAPI Best Practices:
- 모든 라우트는 async
- Dependencies를 활용한 검증
- Service는 session을 받아서 CRUD 직접 사용
- 각 도메인 서비스가 독립적으로 권한 검증 (Orchestrator 패턴)
"""
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status, HTTPException
from sqlmodel import Session

from app.core.auth import CurrentUser, get_current_user
from app.core.constants import TagIncludeMode, ResourceScope
from app.db.session import get_db_transactional
from app.domain.dateutil.service import parse_timezone
from app.domain.schedule.schema.dto import ScheduleRead
from app.domain.schedule.service import ScheduleService
from app.domain.timer.schema.dto import (
    TimerCreate,
    TimerRead,
    TimerUpdate,
)
from app.domain.timer.service import TimerService
from app.domain.timer.model import TimerSession
from app.domain.todo.schema.dto import TodoRead
from app.domain.todo.service import TodoService
from app.domain.visibility.exceptions import AccessDeniedError

router = APIRouter(prefix="/timers", tags=["Timers"])


def _get_timer_related_resources(
        timer: TimerSession,
        include_schedule: bool,
        include_todo: bool,
        session: Session,
        current_user: CurrentUser,
) -> tuple[Optional[ScheduleRead], Optional[TodoRead]]:
    """
    Timer의 연관 리소스(Schedule, Todo)를 각 서비스에서 독립적으로 권한 검증 후 조회
    
    각 도메인 서비스가 자신의 권한 검증 로직을 사용하므로:
    - Schedule 접근 권한: ScheduleService.get_schedule_with_access_check()
    - Todo 접근 권한: TodoService.get_todo_with_access_check()
    
    권한이 없으면 해당 리소스는 null로 반환됩니다.
    """
    schedule_read = None
    todo_read = None

    # Schedule 조회 (권한 검증 포함)
    if include_schedule and timer.schedule_id:
        schedule_service = ScheduleService(session, current_user)
        try:
            schedule, _ = schedule_service.get_schedule_with_access_check(timer.schedule_id)
            schedule_read = schedule_service.to_read_dto(schedule)
        except AccessDeniedError:
            pass  # 접근 권한 없으면 null
        except Exception:
            pass  # 리소스가 없으면 null

    # Todo 조회 (권한 검증 포함)
    if include_todo and timer.todo_id:
        todo_service = TodoService(session, current_user)
        try:
            todo, todo_is_shared = todo_service.get_todo_with_access_check(timer.todo_id)
            # Todo의 연관 Schedule도 권한 검증 후 조회
            todo_schedules = _get_todo_related_schedules(
                todo, todo_is_shared, session, current_user
            )
            todo_read = todo_service.to_read_dto(
                todo, is_shared=todo_is_shared, schedules=todo_schedules
            )
        except AccessDeniedError:
            pass  # 접근 권한 없으면 null
        except Exception:
            pass  # 리소스가 없으면 null

    return schedule_read, todo_read


def _get_todo_related_schedules(
        todo,
        is_shared: bool,
        session: Session,
        current_user: CurrentUser,
) -> List[ScheduleRead]:
    """
    Todo의 연관 Schedule을 권한 검증 후 조회
    """
    from app.crud import schedule as schedule_crud
    
    schedule_owner_id = todo.owner_id if is_shared else current_user.sub
    schedules = schedule_crud.get_schedules_by_source_todo_id(session, todo.id, schedule_owner_id)
    
    schedule_reads = []
    schedule_service = ScheduleService(session, current_user)
    
    for schedule in schedules:
        try:
            # 각 Schedule에 대해 권한 검증
            _, _ = schedule_service.get_schedule_with_access_check(schedule.id)
            schedule_reads.append(schedule_service.to_read_dto(schedule))
        except AccessDeniedError:
            pass  # 접근 권한 없으면 제외
        except Exception:
            pass
    
    return schedule_reads


@router.post("", response_model=TimerRead, status_code=status.HTTP_201_CREATED)
async def create_timer(
        data: TimerCreate,
        include_schedule: bool = Query(
            False,
            description="Schedule 정보 포함 여부 (기본값: false)"
        ),
        include_todo: bool = Query(
            False,
            description="Todo 정보 포함 여부 (기본값: false)"
        ),
        tag_include_mode: TagIncludeMode = Query(
            TagIncludeMode.NONE,
            description="태그 포함 모드: none(포함 안 함), timer_only(타이머 태그만), inherit_from_schedule(스케줄/Todo 태그 상속)"
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
    새 타이머 생성 및 시작
    
    schedule_id, todo_id 모두 Optional:
    - 둘 다 없으면: 독립 타이머
    - schedule_id만: Schedule에 연결된 타이머
    - todo_id만: Todo에 연결된 타이머
    - 둘 다 있으면: Schedule과 Todo 모두에 연결된 타이머
    """
    service = TimerService(session, current_user)
    timer = service.create_timer(data)

    # 연관 리소스 조회 (각 서비스에서 독립적으로 권한 검증)
    schedule_read, todo_read = _get_timer_related_resources(
        timer, include_schedule, include_todo, session, current_user
    )

    # Timer 모델을 TimerRead로 변환
    timer_read = service.to_read_dto(
        timer,
        is_shared=False,
        schedule=schedule_read,
        todo=todo_read,
        tag_include_mode=tag_include_mode,
    )

    # 타임존 변환
    tz_obj = parse_timezone(tz) if tz else None
    return timer_read.to_timezone(tz_obj, validate=False)


@router.get("", response_model=List[TimerRead])
async def list_timers(
        scope: ResourceScope = Query(
            ResourceScope.MINE,
            description="조회 범위: mine(내 타이머만), shared(공유된 타이머만), all(모두)"
        ),
        status_filter: Optional[List[str]] = Query(
            None,
            alias="status",
            description="상태 필터 (RUNNING, PAUSED, COMPLETED, CANCELLED) - 복수 선택 가능"
        ),
        timer_type: Optional[str] = Query(
            None,
            alias="type",
            description="타입 필터: independent(독립 타이머), schedule(Schedule 연결), todo(Todo 연결)"
        ),
        start_date: Optional[datetime] = Query(
            None,
            description="시작 날짜 필터 (started_at 기준, ISO 8601 형식)"
        ),
        end_date: Optional[datetime] = Query(
            None,
            description="종료 날짜 필터 (started_at 기준, ISO 8601 형식)"
        ),
        include_schedule: bool = Query(
            False,
            description="Schedule 정보 포함 여부 (기본값: false)"
        ),
        include_todo: bool = Query(
            False,
            description="Todo 정보 포함 여부 (기본값: false)"
        ),
        tag_include_mode: TagIncludeMode = Query(
            TagIncludeMode.NONE,
            description="태그 포함 모드: none(포함 안 함), timer_only(타이머 태그만), inherit_from_schedule(스케줄/Todo 태그 상속)"
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
    타이머 목록 조회
    
    조회 범위 (scope):
    - mine: 내 타이머만 (기본값)
    - shared: 공유된 타인의 타이머만
    - all: 내 타이머 + 공유된 타이머
    
    필터링 옵션:
    - status: 상태 필터 (RUNNING, PAUSED, COMPLETED, CANCELLED) - 복수 선택 가능
    - type: 타입 필터
      - independent: 독립 타이머 (schedule_id=null AND todo_id=null)
      - schedule: Schedule 연결 타이머 (schedule_id != null)
      - todo: Todo 연결 타이머 (todo_id != null)
    - start_date, end_date: 날짜 범위 필터 (started_at 기준)
    """
    service = TimerService(session, current_user)
    tz_obj = parse_timezone(tz) if tz else None
    result = []

    # status 필터를 소문자로 변환 (API는 대문자, DB는 소문자 저장)
    normalized_status = [s.lower() for s in status_filter] if status_filter else None

    # 내 타이머 조회 (scope=mine 또는 scope=all)
    if scope in (ResourceScope.MINE, ResourceScope.ALL):
        my_timers = service.get_all_timers(
            status=normalized_status,
            timer_type=timer_type,
            start_date=start_date,
            end_date=end_date,
        )
        for timer in my_timers:
            # 연관 리소스 조회 (각 서비스에서 독립적으로 권한 검증)
            schedule_read, todo_read = _get_timer_related_resources(
                timer, include_schedule, include_todo, session, current_user
            )
            timer_read = service.to_read_dto(
                timer,
                is_shared=False,
                schedule=schedule_read,
                todo=todo_read,
                tag_include_mode=tag_include_mode,
            )
            result.append(timer_read.to_timezone(tz_obj, validate=False))

    # 공유된 타이머 조회 (scope=shared 또는 scope=all)
    if scope in (ResourceScope.SHARED, ResourceScope.ALL):
        shared_timers = service.get_shared_timers()
        for timer in shared_timers:
            # status 필터 적용
            if normalized_status and timer.status not in normalized_status:
                continue
            # 날짜 범위 필터 적용
            if start_date and timer.started_at and timer.started_at < start_date:
                continue
            if end_date and timer.started_at and timer.started_at > end_date:
                continue

            # 연관 리소스 조회 (각 서비스에서 독립적으로 권한 검증)
            schedule_read, todo_read = _get_timer_related_resources(
                timer, include_schedule, include_todo, session, current_user
            )
            timer_read = service.to_read_dto(
                timer,
                is_shared=True,
                schedule=schedule_read,
                todo=todo_read,
                tag_include_mode=tag_include_mode,
            )
            result.append(timer_read.to_timezone(tz_obj, validate=False))

    return result


@router.get("/active", response_model=TimerRead)
async def get_user_active_timer(
        include_schedule: bool = Query(
            False,
            description="Schedule 정보 포함 여부 (기본값: false)"
        ),
        include_todo: bool = Query(
            False,
            description="Todo 정보 포함 여부 (기본값: false)"
        ),
        tag_include_mode: TagIncludeMode = Query(
            TagIncludeMode.NONE,
            description="태그 포함 모드: none(포함 안 함), timer_only(타이머 태그만), inherit_from_schedule(스케줄/Todo 태그 상속)"
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
    사용자의 현재 활성 타이머 조회 (RUNNING 또는 PAUSED)
    
    활성 타이머가 없으면 404 반환
    여러 개가 있으면 가장 최근 것 반환
    """
    service = TimerService(session, current_user)
    timer = service.get_user_active_timer()

    if not timer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active timer found"
        )

    # 연관 리소스 조회 (각 서비스에서 독립적으로 권한 검증)
    schedule_read, todo_read = _get_timer_related_resources(
        timer, include_schedule, include_todo, session, current_user
    )

    # Timer 모델을 TimerRead로 변환
    timer_read = service.to_read_dto(
        timer,
        is_shared=False,
        schedule=schedule_read,
        todo=todo_read,
        tag_include_mode=tag_include_mode,
    )

    # 타임존 변환
    tz_obj = parse_timezone(tz) if tz else None
    return timer_read.to_timezone(tz_obj, validate=False)


@router.get("/{timer_id}", response_model=TimerRead)
async def get_timer(
        timer_id: UUID,
        include_schedule: bool = Query(
            False,
            description="Schedule 정보 포함 여부 (기본값: false)"
        ),
        include_todo: bool = Query(
            False,
            description="Todo 정보 포함 여부 (기본값: false)"
        ),
        tag_include_mode: TagIncludeMode = Query(
            TagIncludeMode.NONE,
            description="태그 포함 모드: none(포함 안 함), timer_only(타이머 태그만), inherit_from_schedule(스케줄/Todo 태그 상속)"
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
    타이머 조회 (공유된 타이머 포함)
    
    본인 소유 타이머 또는 공유 접근 권한이 있는 타이머를 조회합니다.
    접근 권한이 없으면 403 Forbidden을 반환합니다.
    """
    service = TimerService(session, current_user)
    timer, is_shared = service.get_timer_with_access_check(timer_id)

    # 연관 리소스 조회 (각 서비스에서 독립적으로 권한 검증)
    schedule_read, todo_read = _get_timer_related_resources(
        timer, include_schedule, include_todo, session, current_user
    )

    # Timer 모델을 TimerRead로 변환
    timer_read = service.to_read_dto(
        timer,
        is_shared=is_shared,
        schedule=schedule_read,
        todo=todo_read,
        tag_include_mode=tag_include_mode,
    )

    # 타임존 변환
    tz_obj = parse_timezone(tz) if tz else None
    return timer_read.to_timezone(tz_obj, validate=False)


@router.patch("/{timer_id}", response_model=TimerRead)
async def update_timer(
        timer_id: UUID,
        data: TimerUpdate,
        include_schedule: bool = Query(
            False,
            description="Schedule 정보 포함 여부 (기본값: false)"
        ),
        include_todo: bool = Query(
            False,
            description="Todo 정보 포함 여부 (기본값: false)"
        ),
        tag_include_mode: TagIncludeMode = Query(
            TagIncludeMode.NONE,
            description="태그 포함 모드: none(포함 안 함), timer_only(타이머 태그만), inherit_from_schedule(스케줄/Todo 태그 상속)"
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
    타이머 메타데이터 업데이트 (title, description, tags)
    """
    service = TimerService(session, current_user)
    timer = service.update_timer(timer_id, data)

    # 연관 리소스 조회 (각 서비스에서 독립적으로 권한 검증)
    schedule_read, todo_read = _get_timer_related_resources(
        timer, include_schedule, include_todo, session, current_user
    )

    # Timer 모델을 TimerRead로 변환
    timer_read = service.to_read_dto(
        timer,
        is_shared=False,
        schedule=schedule_read,
        todo=todo_read,
        tag_include_mode=tag_include_mode,
    )

    # 타임존 변환
    tz_obj = parse_timezone(tz) if tz else None
    return timer_read.to_timezone(tz_obj, validate=False)


@router.patch("/{timer_id}/pause", response_model=TimerRead)
async def pause_timer(
        timer_id: UUID,
        include_schedule: bool = Query(
            False,
            description="Schedule 정보 포함 여부 (기본값: false)"
        ),
        include_todo: bool = Query(
            False,
            description="Todo 정보 포함 여부 (기본값: false)"
        ),
        tag_include_mode: TagIncludeMode = Query(
            TagIncludeMode.NONE,
            description="태그 포함 모드: none(포함 안 함), timer_only(타이머 태그만), inherit_from_schedule(스케줄/Todo 태그 상속)"
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
    타이머 일시정지
    """
    service = TimerService(session, current_user)
    timer = service.pause_timer(timer_id)

    # 연관 리소스 조회 (각 서비스에서 독립적으로 권한 검증)
    schedule_read, todo_read = _get_timer_related_resources(
        timer, include_schedule, include_todo, session, current_user
    )

    # Timer 모델을 TimerRead로 변환
    timer_read = service.to_read_dto(
        timer,
        is_shared=False,
        schedule=schedule_read,
        todo=todo_read,
        tag_include_mode=tag_include_mode,
    )

    # 타임존 변환
    tz_obj = parse_timezone(tz) if tz else None
    return timer_read.to_timezone(tz_obj, validate=False)


@router.patch("/{timer_id}/resume", response_model=TimerRead)
async def resume_timer(
        timer_id: UUID,
        include_schedule: bool = Query(
            False,
            description="Schedule 정보 포함 여부 (기본값: false)"
        ),
        include_todo: bool = Query(
            False,
            description="Todo 정보 포함 여부 (기본값: false)"
        ),
        tag_include_mode: TagIncludeMode = Query(
            TagIncludeMode.NONE,
            description="태그 포함 모드: none(포함 안 함), timer_only(타이머 태그만), inherit_from_schedule(스케줄/Todo 태그 상속)"
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
    타이머 재개
    """
    service = TimerService(session, current_user)
    timer = service.resume_timer(timer_id)

    # 연관 리소스 조회 (각 서비스에서 독립적으로 권한 검증)
    schedule_read, todo_read = _get_timer_related_resources(
        timer, include_schedule, include_todo, session, current_user
    )

    # Timer 모델을 TimerRead로 변환
    timer_read = service.to_read_dto(
        timer,
        is_shared=False,
        schedule=schedule_read,
        todo=todo_read,
        tag_include_mode=tag_include_mode,
    )

    # 타임존 변환
    tz_obj = parse_timezone(tz) if tz else None
    return timer_read.to_timezone(tz_obj, validate=False)


@router.post("/{timer_id}/stop", response_model=TimerRead)
async def stop_timer(
        timer_id: UUID,
        include_schedule: bool = Query(
            False,
            description="Schedule 정보 포함 여부 (기본값: false)"
        ),
        include_todo: bool = Query(
            False,
            description="Todo 정보 포함 여부 (기본값: false)"
        ),
        tag_include_mode: TagIncludeMode = Query(
            TagIncludeMode.NONE,
            description="태그 포함 모드: none(포함 안 함), timer_only(타이머 태그만), inherit_from_schedule(스케줄/Todo 태그 상속)"
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
    타이머 종료
    """
    service = TimerService(session, current_user)
    timer = service.stop_timer(timer_id)

    # 연관 리소스 조회 (각 서비스에서 독립적으로 권한 검증)
    schedule_read, todo_read = _get_timer_related_resources(
        timer, include_schedule, include_todo, session, current_user
    )

    # Timer 모델을 TimerRead로 변환
    timer_read = service.to_read_dto(
        timer,
        is_shared=False,
        schedule=schedule_read,
        todo=todo_read,
        tag_include_mode=tag_include_mode,
    )

    # 타임존 변환
    tz_obj = parse_timezone(tz) if tz else None
    return timer_read.to_timezone(tz_obj, validate=False)


@router.delete("/{timer_id}", status_code=status.HTTP_200_OK)
async def delete_timer(
        timer_id: UUID,
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    타이머 삭제
    """
    service = TimerService(session, current_user)
    service.delete_timer(timer_id)
    return {"ok": True}
