"""
Meeting Router

일정 조율 REST API 엔드포인트
"""
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session

from app.core.auth import CurrentUser, get_current_user, get_optional_current_user
from app.db.session import get_db_transactional
from app.domain.dateutil.service import parse_timezone
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

router = APIRouter(prefix="/meetings", tags=["Meetings"])


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


@router.get("/{meeting_id}", response_model=MeetingRead)
async def read_meeting(
        meeting_id: UUID,
        tz: Optional[str] = Query(
            None,
            alias="timezone",
            description="타임존 (예: UTC, +09:00, Asia/Seoul). 지정하지 않으면 UTC로 반환"
        ),
        session: Session = Depends(get_db_transactional),
        current_user: Optional[CurrentUser] = Depends(get_optional_current_user),
):
    """
    일정 조율 상세 조회
    
    인증 선택적: 접근 권한이 있는 경우 조회 가능합니다.
    - PUBLIC: 인증 없이도 조회 가능 (현재는 인증 필수로 처리)
    - ALLOWED_EMAILS: 허용된 이메일 사용자만 조회 가능 (인증 필수)
    
    Note: PUBLIC 레벨의 비인증 접근은 추후 구현 예정
    """
    # 현재는 인증 필수로 처리 (PUBLIC 비인증 접근은 추후 구현)
    if not current_user:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=401,
            detail="Authentication required"
        )
    
    service = MeetingService(session, current_user)
    meeting, is_shared = service.get_meeting_with_access_check(meeting_id)
    meeting_read = service.to_read_dto(meeting, is_shared=is_shared)
    
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
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    일정 조율 삭제
    
    인증 필수: 소유자만 삭제 가능합니다.
    """
    service = MeetingService(session, current_user)
    service.delete_meeting(meeting_id)
    return {"ok": True}


@router.post("/{meeting_id}/participate", response_model=ParticipantRead, status_code=status.HTTP_201_CREATED)
async def create_participant(
        meeting_id: UUID,
        data: ParticipantCreate,
        tz: Optional[str] = Query(
            None,
            alias="timezone",
            description="타임존 (예: UTC, +09:00, Asia/Seoul). 지정하지 않으면 UTC로 반환"
        ),
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    참여자 등록
    
    인증 필수: 접근 권한이 있는 사용자만 참여 가능합니다.
    """
    service = MeetingService(session, current_user)
    participant = service.create_participant(meeting_id, data)
    participant_read = ParticipantRead.model_validate(participant)
    
    # 타임존 변환
    tz_obj = parse_timezone(tz) if tz else None
    return participant_read.to_timezone(tz_obj)


@router.put("/{meeting_id}/availability", response_model=List[TimeSlotRead])
async def set_availability(
        meeting_id: UUID,
        participant_id: UUID = Query(..., description="참여자 ID"),
        time_slots: List[TimeSlotCreate] = ...,
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    참여자의 가능 시간 설정
    
    인증 필수: 본인의 참여 시간만 설정 가능합니다.
    기존 시간 슬롯을 모두 삭제하고 새로운 시간 슬롯을 설정합니다.
    
    :param meeting_id: 일정 조율 ID
    :param participant_id: 참여자 ID (쿼리 파라미터)
    :param time_slots: 시간 슬롯 리스트 (요청 본문)
    """
    service = MeetingService(session, current_user)
    created_slots = service.set_time_slots(meeting_id, participant_id, time_slots)
    return [TimeSlotRead.model_validate(slot) for slot in created_slots]


@router.get("/{meeting_id}/availability", response_model=List[AvailabilityRead])
async def get_availability(
        meeting_id: UUID,
        tz: Optional[str] = Query(
            None,
            alias="timezone",
            description="타임존 (예: UTC, +09:00, Asia/Seoul). 지정하지 않으면 UTC로 반환"
        ),
        session: Session = Depends(get_db_transactional),
        current_user: Optional[CurrentUser] = Depends(get_optional_current_user),
):
    """
    전체 참여자의 가능 시간 조회
    
    인증 선택적: 접근 권한이 있는 경우 조회 가능합니다.
    """
    if not current_user:
        from app.core.auth import get_current_user as require_auth
        current_user = await require_auth(None, None)
    
    service = MeetingService(session, current_user)
    availability = service.get_availability(meeting_id)
    
    # 타임존 변환
    tz_obj = parse_timezone(tz) if tz else None
    if tz_obj:
        # AvailabilityRead 내부의 ParticipantRead와 TimeSlotRead의 datetime 필드 변환
        converted_availability = []
        for avail in availability:
            converted_participant = avail.participant.to_timezone(tz_obj)
            converted_availability.append(
                AvailabilityRead(
                    participant=converted_participant,
                    time_slots=avail.time_slots,  # TimeSlotRead는 datetime 필드가 없음
                )
            )
        return converted_availability
    
    return availability


@router.get("/{meeting_id}/result", response_model=MeetingResultRead)
async def get_meeting_result(
        meeting_id: UUID,
        tz: Optional[str] = Query(
            None,
            alias="timezone",
            description="타임존 (예: UTC, +09:00, Asia/Seoul). 지정하지 않으면 UTC로 반환"
        ),
        session: Session = Depends(get_db_transactional),
        current_user: Optional[CurrentUser] = Depends(get_optional_current_user),
):
    """
    공통 가능 시간 분석 결과 조회
    
    인증 선택적: 접근 권한이 있는 경우 조회 가능합니다.
    모든 참여자의 시간 선택을 집계하여 겹치는 시간대와 인원 수를 계산합니다.
    """
    if not current_user:
        from app.core.auth import get_current_user as require_auth
        current_user = await require_auth(None, None)
    
    service = MeetingService(session, current_user)
    result = service.get_meeting_result(meeting_id)
    
    # 타임존 변환 (MeetingRead의 datetime 필드만 변환)
    tz_obj = parse_timezone(tz) if tz else None
    if tz_obj:
        converted_meeting = result.meeting.to_timezone(tz_obj)
        return MeetingResultRead(
            meeting=converted_meeting,
            availability_grid=result.availability_grid,
        )
    
    return result
