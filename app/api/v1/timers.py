"""
Timer Router

FastAPI Best Practices:
- 모든 라우트는 async
- Dependencies를 활용한 검증
- Service는 session을 받아서 CRUD 직접 사용
"""
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status, HTTPException
from sqlmodel import Session

from app.core.auth import CurrentUser, get_current_user
from app.core.constants import TagIncludeMode
from app.db.session import get_db_transactional
from app.domain.dateutil.service import parse_timezone
from app.domain.schedule.schema.dto import ScheduleRead
from app.domain.schedule.service import ScheduleService
from app.domain.tag.schema.dto import TagRead
from app.domain.tag.service import TagService
from app.domain.timer.schema.dto import (
    TimerCreate,
    TimerRead,
    TimerUpdate,
)
from app.domain.timer.service import TimerService

router = APIRouter(prefix="/timers", tags=["Timers"])


def get_timer_tags(
        session: Session,
        current_user: CurrentUser,
        timer_id: UUID,
        schedule_id: Optional[UUID],
        todo_id: Optional[UUID],
        tag_include_mode: TagIncludeMode,
) -> list[TagRead]:
    """
    타이머 태그 조회 헬퍼 함수
    
    :param session: DB 세션
    :param current_user: 현재 사용자
    :param timer_id: 타이머 ID
    :param schedule_id: 스케줄 ID (Optional)
    :param todo_id: Todo ID (Optional)
    :param tag_include_mode: 태그 포함 모드
    :return: TagRead 리스트
    """
    if tag_include_mode == TagIncludeMode.NONE:
        return []

    tag_service = TagService(session, current_user)

    if tag_include_mode == TagIncludeMode.TIMER_ONLY:
        tags = tag_service.get_timer_tags(timer_id)
        return [TagRead.model_validate(tag) for tag in tags]

    elif tag_include_mode == TagIncludeMode.INHERIT_FROM_SCHEDULE:
        # 타이머 태그 조회
        timer_tags = tag_service.get_timer_tags(timer_id)
        all_tags = {tag.id: tag for tag in timer_tags}

        # 스케줄 태그 조회 (schedule_id가 있는 경우)
        if schedule_id:
            schedule_service = ScheduleService(session, current_user)
            schedule_tags = schedule_service.get_schedule_tags(schedule_id)
            for tag in schedule_tags:
                all_tags[tag.id] = tag

        # Todo 태그 조회 (todo_id가 있고 schedule_id가 없는 경우)
        if todo_id and not schedule_id:
            from app.domain.todo.service import TodoService
            todo_service = TodoService(session, current_user)
            todo_tags = todo_service.get_todo_tags(todo_id)
            for tag in todo_tags:
                all_tags[tag.id] = tag

        return [TagRead.model_validate(tag) for tag in all_tags.values()]

    return []


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

    # Schedule 정보 처리
    schedule_read = None
    if include_schedule and timer.schedule_id:
        schedule_service = ScheduleService(session, current_user)
        schedule = schedule_service.get_schedule(timer.schedule_id)
        if schedule:
            schedule_read = ScheduleRead.model_validate(schedule)

    # Todo 정보 처리
    todo_read = None
    if include_todo and timer.todo_id:
        from app.domain.todo.service import TodoService
        todo_service = TodoService(session, current_user)
        todo = todo_service.get_todo(timer.todo_id)
        if todo:
            todo_read = todo_service.to_read_dto(todo)

    # Tags 정보 처리
    tags_read = get_timer_tags(session, current_user, timer.id, timer.schedule_id, timer.todo_id, tag_include_mode)

    # Timer 모델을 TimerRead로 변환 (안전한 변환 - 관계 필드 제외)
    timer_read = TimerRead.from_model(
        timer,
        include_schedule=include_schedule,
        schedule=schedule_read,
        include_todo=include_todo,
        todo=todo_read,
        tag_include_mode=tag_include_mode,
        tags=tags_read,
    )

    # 타임존 변환 (from_model로 이미 검증된 인스턴스이므로 validate=False)
    tz_obj = parse_timezone(tz) if tz else None
    return timer_read.to_timezone(tz_obj, validate=False)


@router.get("", response_model=List[TimerRead])
async def list_timers(
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
    
    필터링 옵션:
    - status: 상태 필터 (RUNNING, PAUSED, COMPLETED, CANCELLED) - 복수 선택 가능
    - type: 타입 필터
      - independent: 독립 타이머 (schedule_id=null AND todo_id=null)
      - schedule: Schedule 연결 타이머 (schedule_id != null)
      - todo: Todo 연결 타이머 (todo_id != null)
    - start_date, end_date: 날짜 범위 필터 (started_at 기준)
    """
    service = TimerService(session, current_user)
    
    # status 필터를 소문자로 변환 (API는 대문자, DB는 소문자 저장)
    normalized_status = [s.lower() for s in status_filter] if status_filter else None
    
    timers = service.get_all_timers(
        status=normalized_status,
        timer_type=timer_type,
        start_date=start_date,
        end_date=end_date,
    )

    tz_obj = parse_timezone(tz) if tz else None
    result = []

    for timer in timers:
        # Schedule 정보 처리
        schedule_read = None
        if include_schedule and timer.schedule_id:
            schedule_service = ScheduleService(session, current_user)
            schedule = schedule_service.get_schedule(timer.schedule_id)
            if schedule:
                schedule_read = ScheduleRead.model_validate(schedule)

        # Todo 정보 처리
        todo_read = None
        if include_todo and timer.todo_id:
            from app.domain.todo.service import TodoService
            todo_service = TodoService(session, current_user)
            todo = todo_service.get_todo(timer.todo_id)
            if todo:
                todo_read = todo_service.to_read_dto(todo)

        # Tags 정보 처리
        tags_read = get_timer_tags(session, current_user, timer.id, timer.schedule_id, timer.todo_id, tag_include_mode)

        # Timer 모델을 TimerRead로 변환
        timer_read = TimerRead.from_model(
            timer,
            include_schedule=include_schedule,
            schedule=schedule_read,
            include_todo=include_todo,
            todo=todo_read,
            tag_include_mode=tag_include_mode,
            tags=tags_read,
        )

        # 타임존 변환
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

    # Schedule 정보 처리
    schedule_read = None
    if include_schedule and timer.schedule_id:
        schedule_service = ScheduleService(session, current_user)
        schedule = schedule_service.get_schedule(timer.schedule_id)
        if schedule:
            schedule_read = ScheduleRead.model_validate(schedule)

    # Todo 정보 처리
    todo_read = None
    if include_todo and timer.todo_id:
        from app.domain.todo.service import TodoService
        todo_service = TodoService(session, current_user)
        todo = todo_service.get_todo(timer.todo_id)
        if todo:
            todo_read = todo_service.to_read_dto(todo)

    # Tags 정보 처리
    tags_read = get_timer_tags(session, current_user, timer.id, timer.schedule_id, timer.todo_id, tag_include_mode)

    # Timer 모델을 TimerRead로 변환
    timer_read = TimerRead.from_model(
        timer,
        include_schedule=include_schedule,
        schedule=schedule_read,
        include_todo=include_todo,
        todo=todo_read,
        tag_include_mode=tag_include_mode,
        tags=tags_read,
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
    타이머 조회
    """
    service = TimerService(session, current_user)
    timer = service.get_timer(timer_id)

    # Schedule 정보 처리
    schedule_read = None
    if include_schedule and timer.schedule_id:
        schedule_service = ScheduleService(session, current_user)
        schedule = schedule_service.get_schedule(timer.schedule_id)
        if schedule:
            schedule_read = ScheduleRead.model_validate(schedule)

    # Todo 정보 처리
    todo_read = None
    if include_todo and timer.todo_id:
        from app.domain.todo.service import TodoService
        todo_service = TodoService(session, current_user)
        todo = todo_service.get_todo(timer.todo_id)
        if todo:
            todo_read = todo_service.to_read_dto(todo)

    # Tags 정보 처리
    tags_read = get_timer_tags(session, current_user, timer.id, timer.schedule_id, timer.todo_id, tag_include_mode)

    # Timer 모델을 TimerRead로 변환 (안전한 변환 - 관계 필드 제외)
    timer_read = TimerRead.from_model(
        timer,
        include_schedule=include_schedule,
        schedule=schedule_read,
        include_todo=include_todo,
        todo=todo_read,
        tag_include_mode=tag_include_mode,
        tags=tags_read,
    )

    # 타임존 변환 (from_model로 이미 검증된 인스턴스이므로 validate=False)
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

    # Schedule 정보 처리
    schedule_read = None
    if include_schedule and timer.schedule_id:
        schedule_service = ScheduleService(session, current_user)
        schedule = schedule_service.get_schedule(timer.schedule_id)
        if schedule:
            schedule_read = ScheduleRead.model_validate(schedule)

    # Todo 정보 처리
    todo_read = None
    if include_todo and timer.todo_id:
        from app.domain.todo.service import TodoService
        todo_service = TodoService(session, current_user)
        todo = todo_service.get_todo(timer.todo_id)
        if todo:
            todo_read = todo_service.to_read_dto(todo)

    # Tags 정보 처리
    tags_read = get_timer_tags(session, current_user, timer.id, timer.schedule_id, timer.todo_id, tag_include_mode)

    # Timer 모델을 TimerRead로 변환 (안전한 변환 - 관계 필드 제외)
    timer_read = TimerRead.from_model(
        timer,
        include_schedule=include_schedule,
        schedule=schedule_read,
        include_todo=include_todo,
        todo=todo_read,
        tag_include_mode=tag_include_mode,
        tags=tags_read,
    )

    # 타임존 변환 (from_model로 이미 검증된 인스턴스이므로 validate=False)
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

    # Schedule 정보 처리
    schedule_read = None
    if include_schedule and timer.schedule_id:
        schedule_service = ScheduleService(session, current_user)
        schedule = schedule_service.get_schedule(timer.schedule_id)
        if schedule:
            schedule_read = ScheduleRead.model_validate(schedule)

    # Todo 정보 처리
    todo_read = None
    if include_todo and timer.todo_id:
        from app.domain.todo.service import TodoService
        todo_service = TodoService(session, current_user)
        todo = todo_service.get_todo(timer.todo_id)
        if todo:
            todo_read = todo_service.to_read_dto(todo)

    # Tags 정보 처리
    tags_read = get_timer_tags(session, current_user, timer.id, timer.schedule_id, timer.todo_id, tag_include_mode)

    # Timer 모델을 TimerRead로 변환 (안전한 변환 - 관계 필드 제외)
    timer_read = TimerRead.from_model(
        timer,
        include_schedule=include_schedule,
        schedule=schedule_read,
        include_todo=include_todo,
        todo=todo_read,
        tag_include_mode=tag_include_mode,
        tags=tags_read,
    )

    # 타임존 변환 (from_model로 이미 검증된 인스턴스이므로 validate=False)
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

    # Schedule 정보 처리
    schedule_read = None
    if include_schedule and timer.schedule_id:
        schedule_service = ScheduleService(session, current_user)
        schedule = schedule_service.get_schedule(timer.schedule_id)
        if schedule:
            schedule_read = ScheduleRead.model_validate(schedule)

    # Todo 정보 처리
    todo_read = None
    if include_todo and timer.todo_id:
        from app.domain.todo.service import TodoService
        todo_service = TodoService(session, current_user)
        todo = todo_service.get_todo(timer.todo_id)
        if todo:
            todo_read = todo_service.to_read_dto(todo)

    # Tags 정보 처리
    tags_read = get_timer_tags(session, current_user, timer.id, timer.schedule_id, timer.todo_id, tag_include_mode)

    # Timer 모델을 TimerRead로 변환 (안전한 변환 - 관계 필드 제외)
    timer_read = TimerRead.from_model(
        timer,
        include_schedule=include_schedule,
        schedule=schedule_read,
        include_todo=include_todo,
        todo=todo_read,
        tag_include_mode=tag_include_mode,
        tags=tags_read,
    )

    # 타임존 변환 (from_model로 이미 검증된 인스턴스이므로 validate=False)
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

    # Schedule 정보 처리
    schedule_read = None
    if include_schedule and timer.schedule_id:
        schedule_service = ScheduleService(session, current_user)
        schedule = schedule_service.get_schedule(timer.schedule_id)
        if schedule:
            schedule_read = ScheduleRead.model_validate(schedule)

    # Todo 정보 처리
    todo_read = None
    if include_todo and timer.todo_id:
        from app.domain.todo.service import TodoService
        todo_service = TodoService(session, current_user)
        todo = todo_service.get_todo(timer.todo_id)
        if todo:
            todo_read = todo_service.to_read_dto(todo)

    # Tags 정보 처리
    tags_read = get_timer_tags(session, current_user, timer.id, timer.schedule_id, timer.todo_id, tag_include_mode)

    # Timer 모델을 TimerRead로 변환 (안전한 변환 - 관계 필드 제외)
    timer_read = TimerRead.from_model(
        timer,
        include_schedule=include_schedule,
        schedule=schedule_read,
        include_todo=include_todo,
        todo=todo_read,
        tag_include_mode=tag_include_mode,
        tags=tags_read,
    )

    # 타임존 변환 (from_model로 이미 검증된 인스턴스이므로 validate=False)
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
