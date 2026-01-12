"""
Timer Router

FastAPI Best Practices:
- 모든 라우트는 async
- Dependencies를 활용한 검증
- Service는 session을 받아서 CRUD 직접 사용
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
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
        schedule_id: UUID,
        tag_include_mode: TagIncludeMode,
) -> list[TagRead]:
    """
    타이머 태그 조회 헬퍼 함수
    
    :param session: DB 세션
    :param current_user: 현재 사용자
    :param timer_id: 타이머 ID
    :param schedule_id: 스케줄 ID
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

        # 스케줄 태그 조회
        schedule_service = ScheduleService(session, current_user)
        schedule_tags = schedule_service.get_schedule_tags(schedule_id)

        # 타이머 태그 + 스케줄 태그 합치기 (중복 제거 - ID 기준)
        all_tags = {tag.id: tag for tag in timer_tags}
        for tag in schedule_tags:
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
        tag_include_mode: TagIncludeMode = Query(
            TagIncludeMode.NONE,
            description="태그 포함 모드: none(포함 안 함), timer_only(타이머 태그만), inherit_from_schedule(스케줄 태그 상속)"
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
    
    FastAPI Best Practices:
    - async 라우트 사용
    - 트랜잭션 자동 관리 (context manager)
    - Exception Handler가 예외 처리
    """
    service = TimerService(session, current_user)
    timer = service.create_timer(data)

    # Schedule 정보 처리
    schedule_read = None
    if include_schedule:
        schedule_service = ScheduleService(session, current_user)
        schedule = schedule_service.get_schedule(timer.schedule_id)
        if schedule:
            schedule_read = ScheduleRead.model_validate(schedule)

    # Tags 정보 처리
    tags_read = get_timer_tags(session, current_user, timer.id, timer.schedule_id, tag_include_mode)

    # Timer 모델을 TimerRead로 변환 (안전한 변환 - 관계 필드 제외)
    timer_read = TimerRead.from_model(
        timer,
        include_schedule=include_schedule,
        schedule=schedule_read,
        tag_include_mode=tag_include_mode,
        tags=tags_read,
    )

    # 타임존 변환 (from_model로 이미 검증된 인스턴스이므로 validate=False)
    tz_obj = parse_timezone(tz) if tz else None
    return timer_read.to_timezone(tz_obj, validate=False)


@router.get("/{timer_id}", response_model=TimerRead)
async def get_timer(
        timer_id: UUID,
        include_schedule: bool = Query(
            False,
            description="Schedule 정보 포함 여부 (기본값: false)"
        ),
        tag_include_mode: TagIncludeMode = Query(
            TagIncludeMode.NONE,
            description="태그 포함 모드: none(포함 안 함), timer_only(타이머 태그만), inherit_from_schedule(스케줄 태그 상속)"
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
    if include_schedule:
        schedule_service = ScheduleService(session, current_user)
        schedule = schedule_service.get_schedule(timer.schedule_id)
        if schedule:
            schedule_read = ScheduleRead.model_validate(schedule)

    # Tags 정보 처리
    tags_read = get_timer_tags(session, current_user, timer.id, timer.schedule_id, tag_include_mode)

    # Timer 모델을 TimerRead로 변환 (안전한 변환 - 관계 필드 제외)
    timer_read = TimerRead.from_model(
        timer,
        include_schedule=include_schedule,
        schedule=schedule_read,
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
        tag_include_mode: TagIncludeMode = Query(
            TagIncludeMode.NONE,
            description="태그 포함 모드: none(포함 안 함), timer_only(타이머 태그만), inherit_from_schedule(스케줄 태그 상속)"
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
    if include_schedule:
        schedule_service = ScheduleService(session, current_user)
        schedule = schedule_service.get_schedule(timer.schedule_id)
        if schedule:
            schedule_read = ScheduleRead.model_validate(schedule)

    # Tags 정보 처리
    tags_read = get_timer_tags(session, current_user, timer.id, timer.schedule_id, tag_include_mode)

    # Timer 모델을 TimerRead로 변환 (안전한 변환 - 관계 필드 제외)
    timer_read = TimerRead.from_model(
        timer,
        include_schedule=include_schedule,
        schedule=schedule_read,
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
        tag_include_mode: TagIncludeMode = Query(
            TagIncludeMode.NONE,
            description="태그 포함 모드: none(포함 안 함), timer_only(타이머 태그만), inherit_from_schedule(스케줄 태그 상속)"
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
    if include_schedule:
        schedule_service = ScheduleService(session, current_user)
        schedule = schedule_service.get_schedule(timer.schedule_id)
        if schedule:
            schedule_read = ScheduleRead.model_validate(schedule)

    # Tags 정보 처리
    tags_read = get_timer_tags(session, current_user, timer.id, timer.schedule_id, tag_include_mode)

    # Timer 모델을 TimerRead로 변환 (안전한 변환 - 관계 필드 제외)
    timer_read = TimerRead.from_model(
        timer,
        include_schedule=include_schedule,
        schedule=schedule_read,
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
        tag_include_mode: TagIncludeMode = Query(
            TagIncludeMode.NONE,
            description="태그 포함 모드: none(포함 안 함), timer_only(타이머 태그만), inherit_from_schedule(스케줄 태그 상속)"
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
    if include_schedule:
        schedule_service = ScheduleService(session, current_user)
        schedule = schedule_service.get_schedule(timer.schedule_id)
        if schedule:
            schedule_read = ScheduleRead.model_validate(schedule)

    # Tags 정보 처리
    tags_read = get_timer_tags(session, current_user, timer.id, timer.schedule_id, tag_include_mode)

    # Timer 모델을 TimerRead로 변환 (안전한 변환 - 관계 필드 제외)
    timer_read = TimerRead.from_model(
        timer,
        include_schedule=include_schedule,
        schedule=schedule_read,
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
        tag_include_mode: TagIncludeMode = Query(
            TagIncludeMode.NONE,
            description="태그 포함 모드: none(포함 안 함), timer_only(타이머 태그만), inherit_from_schedule(스케줄 태그 상속)"
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
    if include_schedule:
        schedule_service = ScheduleService(session, current_user)
        schedule = schedule_service.get_schedule(timer.schedule_id)
        if schedule:
            schedule_read = ScheduleRead.model_validate(schedule)

    # Tags 정보 처리
    tags_read = get_timer_tags(session, current_user, timer.id, timer.schedule_id, tag_include_mode)

    # Timer 모델을 TimerRead로 변환 (안전한 변환 - 관계 필드 제외)
    timer_read = TimerRead.from_model(
        timer,
        include_schedule=include_schedule,
        schedule=schedule_read,
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
