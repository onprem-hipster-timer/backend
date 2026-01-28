"""
Timer Router

FastAPI Best Practices:
- 모든 라우트는 async
- Dependencies를 활용한 검증
- Service는 session을 받아서 CRUD 직접 사용

[보안 설계 - Clean Architecture Orchestrator 패턴]
- Router가 orchestrator 역할을 수행
- 각 도메인 서비스는 자신의 리소스만 처리 (서비스 간 직접 호출 금지)
- 연관 리소스는 라우터에서 각 서비스를 독립적으로 호출하여 조합
  - ScheduleService.try_get_schedule_read(): Schedule 권한 검증 후 DTO 반환
  - TodoService.get_todo_with_access_check(): Todo 권한 검증
  - TimerService.to_read_dto(): 검증된 DTO를 주입받아 최종 DTO 생성

[WebSocket 전환 - 2026-01-28]
타이머 제어 작업(생성, 일시정지, 재개, 종료)은 WebSocket 기반으로 전환되었습니다.
- WebSocket 엔드포인트: /ws/timers
- 이유: 멀티 플랫폼 실시간 동기화, 일시정지 이력 추적, 친구 알림 지원
- REST API는 조회/삭제/업데이트만 지원
"""
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status, HTTPException
from sqlmodel import Session

from app.core.auth import CurrentUser, get_current_user
from app.core.constants import TagIncludeMode, ResourceScope
from app.crud import schedule as schedule_crud
from app.db.session import get_db_transactional
from app.domain.dateutil.service import parse_timezone
from app.domain.schedule.service import ScheduleService
from app.domain.timer.schema.dto import (
    TimerRead,
    TimerUpdate,
)
from app.domain.timer.service import TimerService
from app.domain.todo.service import TodoService

router = APIRouter(prefix="/timers", tags=["Timers"])


def _build_timer_read_with_relations(
        timer,
        timer_service: TimerService,
        schedule_service: ScheduleService,
        todo_service: TodoService,
        is_shared: bool = False,
        include_schedule: bool = False,
        include_todo: bool = False,
        tag_include_mode: Optional[TagIncludeMode] = None,
) -> TimerRead:
    """
    Timer와 연관 리소스를 조립하여 TimerRead DTO 생성 (라우터 orchestrator 헬퍼)
    
    [Clean Architecture] 라우터가 각 도메인 서비스를 독립적으로 호출합니다.
    - 서비스 간 직접 호출 없음
    - 각 서비스는 자신의 도메인만 처리
    
    :param timer: Timer 모델
    :param timer_service: TimerService 인스턴스
    :param schedule_service: ScheduleService 인스턴스
    :param todo_service: TodoService 인스턴스
    :param is_shared: 공유된 리소스인지 여부
    :param include_schedule: Schedule 정보 포함 여부
    :param include_todo: Todo 정보 포함 여부
    :param tag_include_mode: 태그 포함 모드
    :return: TimerRead DTO
    """
    from app.domain.visibility.exceptions import AccessDeniedError
    from app.domain.todo.exceptions import TodoNotFoundError

    schedule_read = None
    todo_read = None

    # Schedule 조회 (ScheduleService에서 권한 검증)
    if include_schedule and timer.schedule_id:
        schedule_read = schedule_service.try_get_schedule_read(timer.schedule_id)

    # Todo 조회 (TodoService에서 권한 검증 + 연관 Schedule 조회)
    if include_todo and timer.todo_id:
        try:
            todo, todo_is_shared = todo_service.get_todo_with_access_check(timer.todo_id)

            # Todo의 연관 Schedule 조회 (각 Schedule은 ScheduleService에서 권한 검증)
            schedule_owner_id = todo.owner_id if todo_is_shared else todo_service.owner_id
            schedules = schedule_crud.get_schedules_by_source_todo_id(
                todo_service.session, todo.id, schedule_owner_id
            )

            schedule_reads = []
            for schedule in schedules:
                s_read = schedule_service.try_get_schedule_read(schedule.id)
                if s_read:
                    schedule_reads.append(s_read)

            todo_read = todo_service.to_read_dto(todo, is_shared=todo_is_shared, schedules=schedule_reads)
        except (TodoNotFoundError, AccessDeniedError):
            # 접근 불가한 Todo는 None으로 처리
            pass

    return timer_service.to_read_dto(
        timer,
        is_shared=is_shared,
        schedule=schedule_read,
        todo=todo_read,
        tag_include_mode=tag_include_mode,
    )


# [WebSocket 전환] 타이머 생성은 WebSocket으로 이동
# 엔드포인트: /ws/timers
# 메시지: { "type": "timer.create", "payload": { ... } }


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
    timer_service = TimerService(session, current_user)
    schedule_service = ScheduleService(session, current_user)
    todo_service = TodoService(session, current_user)

    tz_obj = parse_timezone(tz) if tz else None
    result = []

    # status 필터를 대문자로 변환 (API는 대문자, DB도 대문자 저장)
    normalized_status = [s.upper() for s in status_filter] if status_filter else None

    # 내 타이머 조회 (scope=mine 또는 scope=all)
    if scope in (ResourceScope.MINE, ResourceScope.ALL):
        my_timers = timer_service.get_all_timers(
            status=normalized_status,
            timer_type=timer_type,
            start_date=start_date,
            end_date=end_date,
        )
        for timer in my_timers:
            timer_read = _build_timer_read_with_relations(
                timer,
                timer_service=timer_service,
                schedule_service=schedule_service,
                todo_service=todo_service,
                is_shared=False,
                include_schedule=include_schedule,
                include_todo=include_todo,
                tag_include_mode=tag_include_mode,
            )
            result.append(timer_read.to_timezone(tz_obj, validate=False))

    # 공유된 타이머 조회 (scope=shared 또는 scope=all)
    if scope in (ResourceScope.SHARED, ResourceScope.ALL):
        shared_timers = timer_service.get_shared_timers()
        for timer in shared_timers:
            # status 필터 적용
            if normalized_status and timer.status not in normalized_status:
                continue
            # 날짜 범위 필터 적용
            if start_date and timer.started_at and timer.started_at < start_date:
                continue
            if end_date and timer.started_at and timer.started_at > end_date:
                continue

            timer_read = _build_timer_read_with_relations(
                timer,
                timer_service=timer_service,
                schedule_service=schedule_service,
                todo_service=todo_service,
                is_shared=True,
                include_schedule=include_schedule,
                include_todo=include_todo,
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
    timer_service = TimerService(session, current_user)
    schedule_service = ScheduleService(session, current_user)
    todo_service = TodoService(session, current_user)

    timer = timer_service.get_user_active_timer()

    if not timer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active timer found"
        )

    # 연관 리소스 조회 및 DTO 생성 (라우터에서 orchestration)
    timer_read = _build_timer_read_with_relations(
        timer,
        timer_service=timer_service,
        schedule_service=schedule_service,
        todo_service=todo_service,
        is_shared=False,
        include_schedule=include_schedule,
        include_todo=include_todo,
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
    timer_service = TimerService(session, current_user)
    schedule_service = ScheduleService(session, current_user)
    todo_service = TodoService(session, current_user)

    timer, is_shared = timer_service.get_timer_with_access_check(timer_id)

    # 연관 리소스 조회 및 DTO 생성 (라우터에서 orchestration)
    timer_read = _build_timer_read_with_relations(
        timer,
        timer_service=timer_service,
        schedule_service=schedule_service,
        todo_service=todo_service,
        is_shared=is_shared,
        include_schedule=include_schedule,
        include_todo=include_todo,
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
    timer_service = TimerService(session, current_user)
    schedule_service = ScheduleService(session, current_user)
    todo_service = TodoService(session, current_user)

    timer = timer_service.update_timer(timer_id, data)

    # 연관 리소스 조회 및 DTO 생성 (라우터에서 orchestration)
    timer_read = _build_timer_read_with_relations(
        timer,
        timer_service=timer_service,
        schedule_service=schedule_service,
        todo_service=todo_service,
        is_shared=False,
        include_schedule=include_schedule,
        include_todo=include_todo,
        tag_include_mode=tag_include_mode,
    )

    # 타임존 변환
    tz_obj = parse_timezone(tz) if tz else None
    return timer_read.to_timezone(tz_obj, validate=False)


# [WebSocket 전환] 타이머 제어 작업은 WebSocket으로 이동
# 엔드포인트: /ws/timers
# 메시지:
#   - 일시정지: { "type": "timer.pause", "payload": { "timer_id": "uuid" } }
#   - 재개: { "type": "timer.resume", "payload": { "timer_id": "uuid" } }
#   - 종료: { "type": "timer.stop", "payload": { "timer_id": "uuid" } }


@router.delete("/{timer_id}", status_code=status.HTTP_200_OK)
async def delete_timer(
        timer_id: UUID,
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    타이머 삭제
    """
    timer_service = TimerService(session, current_user)
    timer_service.delete_timer(timer_id)
    return {"ok": True}
