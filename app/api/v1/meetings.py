"""
Meeting Router

일정 조율 REST API 엔드포인트

- router: 회원만 (인증 라우터, app/api/v1/__init__.py). 생성·목록·수정·삭제·참여자 빼기
- shared_router: 회원, 그 미팅의 게스트, 로그인하지 않은 방문자. 조회·참여·가능 시간·결과
  - 회원: 인증 라우터와 같은 확인(get_current_user_synced) 뒤 공개 범위로 판정한다 (MeetingService)
  - 게스트: require_guest_access(MEETING, "meeting_id")가 판정한다 (MeetingGuestService)
  - 로그인하지 않은 방문자: 미팅 조회와 결과만 (MeetingVisitorService). 참여·가능 시간은 401
  - 게스트와 방문자의 응답에는 회원의 sub(owner_id, 참여자의 user_id)를 넣지 않는다

테스트: tests/domain/guest/test_meeting_access.py, tests/domain/guest/test_meeting_participation.py,
tests/domain/guest/test_meeting_participant_removal.py
"""
from dataclasses import dataclass
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlmodel import Session
from starlette.concurrency import run_in_threadpool

import app.core.config as app_config
from app.core.auth import (
    CurrentUser,
    authenticate_request,
    ensure_member,
    get_current_user,
    get_current_user_synced,
    security,
)
from app.db.session import CommittingSession, get_db_transactional
from app.domain.dateutil.service import parse_timezone
from app.domain.guest.dependencies import get_current_guest, require_guest_access
from app.domain.guest.model import Guest
from app.domain.guest.service import discard_guest, discard_resource_guests
from app.domain.meeting.result_service import MeetingResultService
from app.domain.meeting.schema.dto import (
    MeetingCreate,
    MeetingRead,
    MeetingUpdate,
    ParticipantCreate,
    ParticipantRead,
    TimeSlotCreate,
    TimeSlotRead,
    AvailabilityRead,
    MeetingResultRead,
)
from app.domain.meeting.service import MeetingService
from app.domain.meeting.visitor_service import MeetingGuestService, MeetingVisitorService
from app.domain.visibility.enums import ResourceType

router = APIRouter(prefix="/meetings", tags=["Meetings"])
shared_router = APIRouter(prefix="/meetings", tags=["Meetings"])

_meeting_guest = require_guest_access(ResourceType.MEETING, "meeting_id")


@dataclass(frozen=True)
class MeetingCaller:
    """shared_router 경로의 호출자. 둘 다 None이면 로그인하지 않은 방문자"""
    user: CurrentUser | None = None  # 회원
    guest: Guest | None = None  # 이 미팅의 게스트


async def get_meeting_principal(
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> CurrentUser | None:
    """요청 토큰의 주체 (회원·게스트를 가리지 않는다). 토큰이 없으면 None, 검증에 실패하면 401"""
    if credentials is None and app_config.settings.OIDC_ENABLED:
        return None
    return await authenticate_request(request, credentials)


async def get_meeting_caller(
        request: Request,
        principal: CurrentUser | None = Depends(get_meeting_principal),
        credentials: HTTPAuthorizationCredentials | None = Depends(security),
        session: Session = Depends(get_db_transactional),
) -> MeetingCaller:
    """게스트 토큰이면 이 미팅의 게스트인지(require_guest_access), 회원이면 인증 라우터와 같은 확인을 한다"""
    if principal is None:
        return MeetingCaller()
    if principal.is_guest:
        return MeetingCaller(guest=await _meeting_guest(request, await get_current_guest(request, credentials)))
    if app_config.settings.OIDC_ENABLED:
        ensure_member(principal)
    await run_in_threadpool(get_current_user_synced, request, principal, session)
    return MeetingCaller(user=principal)


async def get_signed_in_meeting_caller(caller: MeetingCaller = Depends(get_meeting_caller)) -> MeetingCaller:
    """로그인하지 않았으면 401"""
    if caller.user is None and caller.guest is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return caller


@router.post("", response_model=MeetingRead, status_code=status.HTTP_201_CREATED)
async def create_meeting(
        data: MeetingCreate,
        tz: Optional[str] = Query(
            None,
            alias="timezone",
            description="타임존 (예: UTC, +09:00, Asia/Seoul). 지정하지 않으면 UTC로 반환"
        ),
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    일정 조율 생성
    
    인증 필수: 일정 조율 생성자는 소유자가 됩니다.
    """
    service = MeetingService(session, current_user)
    meeting = service.create_meeting(data)
    meeting_read = service.to_read_dto(meeting, is_shared=False)

    # 타임존 변환
    tz_obj = parse_timezone(tz) if tz else None
    return meeting_read.to_timezone(tz_obj)


@router.get("", response_model=List[MeetingRead])
async def read_meetings(
        tz: Optional[str] = Query(
            None,
            alias="timezone",
            description="타임존 (예: UTC, +09:00, Asia/Seoul). 지정하지 않으면 UTC로 반환"
        ),
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    내가 생성한 일정 조율 목록 조회
    
    인증 필수: 본인이 생성한 일정 조율만 조회됩니다.
    """
    service = MeetingService(session, current_user)
    meetings = service.get_all_meetings()

    # 타임존 변환
    tz_obj = parse_timezone(tz) if tz else None
    return [service.to_read_dto(m, is_shared=False).to_timezone(tz_obj) for m in meetings]


@shared_router.get("/{meeting_id}", response_model=MeetingRead)
async def read_meeting(
        meeting_id: UUID,
        tz: Optional[str] = Query(
            None,
            alias="timezone",
            description="타임존 (예: UTC, +09:00, Asia/Seoul). 지정하지 않으면 UTC로 반환"
        ),
        session: Session = Depends(get_db_transactional),
        caller: MeetingCaller = Depends(get_meeting_caller),
):
    """
    일정 조율 상세 조회

    인증 선택적: 회원은 접근 권한이 있으면, 그 미팅의 게스트와 로그인하지 않은 방문자는 PUBLIC이면 조회할 수 있습니다.
    게스트와 방문자의 응답에는 owner_id가 없습니다(null).
    """
    if caller.user is not None:
        service = MeetingService(session, caller.user)
        meeting, is_shared = service.get_meeting_with_access_check(meeting_id)
        meeting_read = service.to_read_dto(meeting, is_shared=is_shared)
    else:
        visitor = MeetingVisitorService(session)
        meeting_read = visitor.to_read_dto(visitor.get_meeting(meeting_id))

    # 타임존 변환
    tz_obj = parse_timezone(tz) if tz else None
    return meeting_read.to_timezone(tz_obj)


@router.patch("/{meeting_id}", response_model=MeetingRead)
async def update_meeting(
        meeting_id: UUID,
        data: MeetingUpdate,
        tz: Optional[str] = Query(
            None,
            alias="timezone",
            description="타임존 (예: UTC, +09:00, Asia/Seoul). 지정하지 않으면 UTC로 반환"
        ),
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    일정 조율 수정
    
    인증 필수: 소유자만 수정 가능합니다.
    """
    service = MeetingService(session, current_user)
    meeting = service.update_meeting(meeting_id, data)
    meeting_read = service.to_read_dto(meeting, is_shared=False)

    # 타임존 변환
    tz_obj = parse_timezone(tz) if tz else None
    return meeting_read.to_timezone(tz_obj)


@router.delete("/{meeting_id}", status_code=status.HTTP_200_OK)
async def delete_meeting(
        meeting_id: UUID,
        background_tasks: BackgroundTasks,
        session: Session = CommittingSession,
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    일정 조율 삭제
    
    인증 필수: 소유자만 삭제 가능합니다. 삭제를 커밋한 뒤 그 미팅의 게스트를 모두 폐기합니다.
    """
    service = MeetingService(session, current_user)
    service.delete_meeting(meeting_id)
    background_tasks.add_task(discard_resource_guests, ResourceType.MEETING, meeting_id)
    return {"ok": True}


@router.delete("/{meeting_id}/participants/{participant_id}", status_code=status.HTTP_200_OK)
async def remove_participant(
        meeting_id: UUID,
        participant_id: UUID,
        session: Session = CommittingSession,
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    참여자 빼기

    인증 필수: 소유자만 뺄 수 있습니다(자기 참여자 포함). 다른 회원에게는 없는 미팅과 같은 404입니다.
    참여자와 그 가능 시간이 지워집니다. 게스트 참여자는 그 게스트를 폐기합니다(게스트 자기 삭제와 같다).
    """
    guest_identity_id = MeetingService(session, current_user).remove_participant(meeting_id, participant_id)
    if guest_identity_id is not None:
        await discard_guest(guest_identity_id)
    return {"ok": True}


@shared_router.post(
    "/{meeting_id}/participate", response_model=ParticipantRead, status_code=status.HTTP_201_CREATED,
)
async def create_participant(
        meeting_id: UUID,
        data: ParticipantCreate,
        response: Response,
        tz: Optional[str] = Query(
            None,
            alias="timezone",
            description="타임존 (예: UTC, +09:00, Asia/Seoul). 지정하지 않으면 UTC로 반환"
        ),
        session: Session = Depends(get_db_transactional),
        caller: MeetingCaller = Depends(get_signed_in_meeting_caller),
):
    """
    참여자 등록

    인증 필수: 접근 권한이 있는 회원과 그 미팅의 게스트가 참여할 수 있습니다.
    미팅마다 회원당·게스트당 참여자는 한 명입니다. 처음 등록하면 201, 이미 참여했으면 기존 참여자를 200으로 반환합니다.
    회원은 다시 등록하면 표시 이름을 보낸 값으로 바꿉니다. 게스트 참여자의 표시 이름은 보낸 값과 상관없이 게스트 이름입니다.
    """
    if caller.guest is not None:
        participant, created = MeetingGuestService(session, caller.guest).create_participant(meeting_id)
    else:
        participant, created = MeetingService(session, caller.user).create_participant(meeting_id, data)
    if not created:
        response.status_code = status.HTTP_200_OK
    participant_read = ParticipantRead.from_participant(participant, participant.meeting.owner_id)

    # 타임존 변환
    tz_obj = parse_timezone(tz) if tz else None
    return participant_read.to_timezone(tz_obj)


@shared_router.put("/{meeting_id}/availability", response_model=List[TimeSlotRead])
async def set_availability(
        meeting_id: UUID,
        participant_id: UUID = Query(..., description="참여자 ID"),
        time_slots: List[TimeSlotCreate] = ...,
        tz: Optional[str] = Query(
            None,
            alias="timezone",
            description="타임존 (예: UTC, +09:00, Asia/Seoul). 지정하지 않으면 UTC로 반환"
        ),
        session: Session = Depends(get_db_transactional),
        caller: MeetingCaller = Depends(get_signed_in_meeting_caller),
):
    """
    참여자의 가능 시간 설정
    
    인증 필수: 회원과 그 미팅의 게스트가 본인의 참여 시간만 설정 가능합니다.
    기존 시간 슬롯을 모두 삭제하고 새로운 시간 슬롯을 설정합니다.
    슬롯은 반열린 구간 [start_time, end_time)이고 시간대가 없는 값은 UTC로 읽습니다. 보낸 구간 그대로 저장합니다.
    슬롯 수는 미팅의 칸 수까지입니다 (넘으면 422). 슬롯이 미팅의 날짜·시간 범위나 칸에 맞는지는 검사하지 않습니다.
    
    :param meeting_id: 일정 조율 ID
    :param participant_id: 참여자 ID (쿼리 파라미터)
    :param time_slots: 시간 슬롯 리스트 (요청 본문)
    """
    if caller.guest is not None:
        service = MeetingGuestService(session, caller.guest)
    else:
        service = MeetingService(session, caller.user)
    created_slots = service.set_time_slots(meeting_id, participant_id, time_slots)

    # 타임존 변환
    tz_obj = parse_timezone(tz) if tz else None
    return [TimeSlotRead.model_validate(slot).to_timezone(tz_obj) for slot in created_slots]


@shared_router.get("/{meeting_id}/availability", response_model=List[AvailabilityRead])
async def get_availability(
        meeting_id: UUID,
        tz: Optional[str] = Query(
            None,
            alias="timezone",
            description="타임존 (예: UTC, +09:00, Asia/Seoul). 지정하지 않으면 UTC로 반환"
        ),
        session: Session = Depends(get_db_transactional),
        caller: MeetingCaller = Depends(get_signed_in_meeting_caller),
):
    """
    전체 참여자의 가능 시간 조회

    인증 필수: 접근 권한이 있는 회원과 그 미팅의 게스트가 조회할 수 있습니다. 게스트의 응답에는 참여자의 user_id가 없습니다(null).
    """
    if caller.guest is not None:
        availability = MeetingGuestService(session, caller.guest).get_availability(meeting_id)
    else:
        availability = MeetingResultService(session, caller.user).get_availability(meeting_id)

    # 타임존 변환
    tz_obj = parse_timezone(tz) if tz else None
    return [avail.to_timezone(tz_obj) for avail in availability]


@shared_router.get("/{meeting_id}/result", response_model=MeetingResultRead)
async def get_meeting_result(
        meeting_id: UUID,
        tz: Optional[str] = Query(
            None,
            alias="timezone",
            description="타임존 (예: UTC, +09:00, Asia/Seoul). 지정하지 않으면 UTC로 반환"
        ),
        session: Session = Depends(get_db_transactional),
        caller: MeetingCaller = Depends(get_meeting_caller),
):
    """
    공통 가능 시간 분석 결과 조회

    인증 선택적: 회원은 접근 권한이 있으면, 그 미팅의 게스트와 로그인하지 않은 방문자는 PUBLIC이면 조회할 수 있습니다.
    미팅의 시간대에서 미팅 날짜(제외 날짜를 뺀 기간)·하루 범위·시간 단위로 만든 칸마다, 그 칸을 모두 덮는 가능 시간을 가진 참여자 수를 셉니다.
    게스트와 방문자의 응답에는 owner_id가 없습니다(null).
    """
    if caller.user is not None:
        result = MeetingResultService(session, caller.user).get_meeting_result(meeting_id)
    else:
        result = MeetingVisitorService(session).get_meeting_result(meeting_id)

    # 타임존 변환
    tz_obj = parse_timezone(tz) if tz else None
    return result.to_timezone(tz_obj)
