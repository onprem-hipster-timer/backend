"""
Meeting Service

일정 조율 서비스 비즈니스 로직 (CRUD + 참여자 관리)
"""
from typing import List
from uuid import UUID

from sqlmodel import Session

from app.core.auth import CurrentUser
from app.crud import meeting as crud
from app.crud import visibility as visibility_crud
from app.domain.meeting.exceptions import (
    MeetingNotFoundError,
    MeetingParticipantNotFoundError,
)
from app.domain.meeting.schema.dto import (
    MeetingCreate,
    MeetingUpdate,
    MeetingRead,
    ParticipantCreate,
    TimeSlotCreate,
)
from app.domain.visibility.enums import ResourceType
from app.domain.visibility.exceptions import AccessDeniedError
from app.domain.visibility.service import VisibilityService
from app.models.meeting import Meeting, MeetingParticipant, MeetingTimeSlot


class MeetingService:
    """
    Meeting Service - CRUD + 참여자 관리

    일정 조율의 생성/조회/수정/삭제 및 참여자 관리를 담당합니다.
    분석 로직은 MeetingResultService에서 처리합니다.
    """

    def __init__(self, session: Session, current_user: CurrentUser):
        self.session = session
        self.current_user = current_user
        self.owner_id = current_user.sub

    def create_meeting(self, data: MeetingCreate) -> Meeting:
        """
        일정 조율 생성
        
        :param data: 일정 조율 생성 데이터
        :return: 생성된 일정 조율
        """
        meeting = crud.create_meeting(self.session, data, self.owner_id)
        return meeting

    def get_meeting(self, meeting_id: UUID) -> Meeting:
        """
        일정 조율 조회 (본인 소유만)
        
        :param meeting_id: 일정 조율 ID
        :return: 일정 조율
        :raises MeetingNotFoundError: 일정 조율을 찾을 수 없는 경우
        """
        meeting = crud.get_meeting(self.session, meeting_id, self.owner_id)
        if not meeting:
            raise MeetingNotFoundError()
        return meeting

    def get_meeting_with_access_check(self, meeting_id: UUID) -> tuple[Meeting, bool]:
        """
        일정 조율 조회 (공유 리소스 접근 제어 포함)
        
        본인 소유이거나 공유 접근 권한이 있는 경우 반환합니다.
        
        :param meeting_id: 일정 조율 ID
        :return: (일정 조율, is_shared) 튜플
        :raises MeetingNotFoundError: 일정 조율을 찾을 수 없는 경우
        :raises AccessDeniedError: 접근 권한이 없는 경우
        """
        # 먼저 ID로만 조회 (소유자 무관)
        meeting = crud.get_meeting_by_id(self.session, meeting_id)
        if not meeting:
            raise MeetingNotFoundError()

        # 본인 소유인 경우
        if meeting.owner_id == self.owner_id:
            return meeting, False

        # 타인 소유인 경우 접근 권한 확인
        visibility_service = VisibilityService(self.session, self.current_user)
        visibility_service.require_access(
            resource_type=ResourceType.MEETING,
            resource_id=meeting_id,
            owner_id=meeting.owner_id,
        )

        return meeting, True

    def get_all_meetings(self) -> List[Meeting]:
        """
        모든 일정 조율 조회 (본인 소유만)
        
        :return: 일정 조율 리스트
        """
        return crud.get_meetings(self.session, self.owner_id)

    def update_meeting(self, meeting_id: UUID, data: MeetingUpdate) -> Meeting:
        """
        일정 조율 업데이트
        
        :param meeting_id: 일정 조율 ID
        :param data: 업데이트 데이터
        :return: 업데이트된 일정 조율
        :raises MeetingNotFoundError: 일정 조율을 찾을 수 없는 경우
        """
        meeting = crud.get_meeting(self.session, meeting_id, self.owner_id)
        if not meeting:
            raise MeetingNotFoundError()

        updated_meeting = crud.update_meeting(self.session, meeting, data)
        return updated_meeting

    def delete_meeting(self, meeting_id: UUID) -> None:
        """
        일정 조율 삭제
        
        :param meeting_id: 일정 조율 ID
        :raises MeetingNotFoundError: 일정 조율을 찾을 수 없는 경우
        """
        meeting = crud.get_meeting(self.session, meeting_id, self.owner_id)
        if not meeting:
            raise MeetingNotFoundError()

        # 접근권한 설정 삭제
        visibility_crud.delete_visibility_by_resource(
            self.session, ResourceType.MEETING, meeting_id
        )

        crud.delete_meeting(self.session, meeting)

    def create_participant(
            self,
            meeting_id: UUID,
            data: ParticipantCreate,
    ) -> MeetingParticipant:
        """
        참여자 등록
        
        :param meeting_id: 일정 조율 ID
        :param data: 참여자 생성 데이터
        :return: 생성된 참여자
        :raises MeetingNotFoundError: 일정 조율을 찾을 수 없는 경우
        :raises AccessDeniedError: 접근 권한이 없는 경우
        """
        # 접근 권한 확인
        self.get_meeting_with_access_check(meeting_id)

        # 참여자 생성 (user_id는 현재 사용자 ID)
        participant = crud.create_participant(
            self.session,
            meeting_id,
            user_id=self.owner_id,
            display_name=data.display_name,
        )

        return participant

    def get_participant(
            self,
            meeting_id: UUID,
            participant_id: UUID,
    ) -> MeetingParticipant:
        """
        참여자 조회
        
        :param meeting_id: 일정 조율 ID
        :param participant_id: 참여자 ID
        :return: 참여자
        :raises MeetingNotFoundError: 일정 조율을 찾을 수 없는 경우
        :raises AccessDeniedError: 접근 권한이 없는 경우
        :raises MeetingParticipantNotFoundError: 참여자를 찾을 수 없는 경우
        """
        # 접근 권한 확인
        self.get_meeting_with_access_check(meeting_id)

        participant = crud.get_participant(
            self.session,
            meeting_id,
            participant_id,
        )
        if not participant:
            raise MeetingParticipantNotFoundError()

        return participant

    def get_participants(self, meeting_id: UUID) -> List[MeetingParticipant]:
        """
        참여자 목록 조회
        
        :param meeting_id: 일정 조율 ID
        :return: 참여자 리스트
        :raises MeetingNotFoundError: 일정 조율을 찾을 수 없는 경우
        :raises AccessDeniedError: 접근 권한이 없는 경우
        """
        # 접근 권한 확인
        self.get_meeting_with_access_check(meeting_id)

        return crud.get_participants(self.session, meeting_id)

    def set_time_slots(
            self,
            meeting_id: UUID,
            participant_id: UUID,
            time_slots: List[TimeSlotCreate],
    ) -> List[MeetingTimeSlot]:
        """
        참여자의 가능 시간 설정
        
        기존 시간 슬롯을 모두 삭제하고 새로운 시간 슬롯을 설정합니다.
        
        :param meeting_id: 일정 조율 ID
        :param participant_id: 참여자 ID
        :param time_slots: 시간 슬롯 리스트
        :return: 생성된 시간 슬롯 리스트
        :raises MeetingNotFoundError: 일정 조율을 찾을 수 없는 경우
        :raises AccessDeniedError: 접근 권한이 없는 경우
        :raises MeetingParticipantNotFoundError: 참여자를 찾을 수 없는 경우
        """
        # 접근 권한 확인
        self.get_meeting_with_access_check(meeting_id)

        # 참여자 확인
        participant = self.get_participant(meeting_id, participant_id)

        # 참여자가 본인인지 확인 (본인만 수정 가능)
        if participant.user_id != self.owner_id:
            raise AccessDeniedError()

        # 기존 시간 슬롯 삭제
        crud.delete_participant_time_slots(self.session, participant_id)

        # 새로운 시간 슬롯 생성
        created_slots = []
        for slot_data in time_slots:
            slot = crud.create_time_slot(
                self.session,
                participant_id,
                slot_data.slot_date,
                slot_data.start_time,
                slot_data.end_time,
            )
            created_slots.append(slot)

        return created_slots

    def to_read_dto(
            self,
            meeting: Meeting,
            is_shared: bool = False,
    ) -> MeetingRead:
        """
        Meeting을 MeetingRead DTO로 변환하고 접근권한 정보를 채웁니다.
        
        :param meeting: Meeting 모델
        :param is_shared: 공유된 리소스인지 여부
        :return: MeetingRead DTO (접근권한 정보 포함)
        """
        meeting_read = MeetingRead.model_validate(meeting)
        meeting_read.owner_id = meeting.owner_id
        meeting_read.is_shared = is_shared

        # 접근권한 레벨 조회
        visibility = visibility_crud.get_visibility_by_resource(
            self.session, ResourceType.MEETING, meeting.id
        )
        if visibility:
            meeting_read.visibility_level = visibility.level

        return meeting_read
