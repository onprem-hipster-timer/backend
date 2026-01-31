"""
Meeting Service

일정 조율 서비스 비즈니스 로직
"""
from datetime import date, time, timedelta
from typing import List, Optional
from uuid import UUID

from sqlmodel import Session

from app.core.auth import CurrentUser
from app.crud import meeting as crud
from app.crud import visibility as visibility_crud
from app.domain.meeting.exceptions import (
    MeetingNotFoundError,
    MeetingParticipantNotFoundError,
)
from app.domain.visibility.exceptions import AccessDeniedError
from app.domain.meeting.schema.dto import (
    MeetingCreate,
    MeetingUpdate,
    MeetingRead,
    ParticipantCreate,
    ParticipantRead,
    TimeSlotCreate,
    TimeSlotRead,
    AvailabilityRead,
    MeetingResultRead,
)
from app.domain.visibility.enums import VisibilityLevel, ResourceType
from app.domain.visibility.service import VisibilityService
from app.models.meeting import Meeting, MeetingParticipant, MeetingTimeSlot


class MeetingService:
    """
    Meeting Service - 비즈니스 로직
    
    일정 조율 서비스의 핵심 비즈니스 로직을 담당합니다.
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

        # 가시성 설정
        if data.visibility:
            visibility_service = VisibilityService(self.session, self.current_user)
            visibility_service.set_visibility(
                resource_type=ResourceType.MEETING,
                resource_id=meeting.id,
                level=data.visibility.level,
                allowed_user_ids=data.visibility.allowed_user_ids,
                allowed_emails=data.visibility.allowed_emails,
                allowed_domains=data.visibility.allowed_domains,
            )

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

        # 설정된 필드만 가져오기 (exclude_unset=True)
        update_dict = data.model_dump(exclude_unset=True)

        # 가시성 업데이트 (visibility가 설정된 경우에만)
        visibility_updated = 'visibility' in update_dict
        if visibility_updated and update_dict['visibility']:
            visibility_data = update_dict['visibility']
            visibility_service = VisibilityService(self.session, self.current_user)
            visibility_service.set_visibility(
                resource_type=ResourceType.MEETING,
                resource_id=meeting.id,
                level=visibility_data.level,
                allowed_user_ids=visibility_data.allowed_user_ids,
                allowed_emails=visibility_data.allowed_emails,
                allowed_domains=visibility_data.allowed_domains,
            )
            del update_dict['visibility']  # CRUD에 전달하지 않음

        # 변환된 dict로 MeetingUpdate 재생성
        update_data = MeetingUpdate(**update_dict)

        updated_meeting = crud.update_meeting(self.session, meeting, update_data)
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

        # 가시성 설정 삭제
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

    def get_availability(self, meeting_id: UUID) -> List[AvailabilityRead]:
        """
        전체 참여자의 가능 시간 조회
        
        :param meeting_id: 일정 조율 ID
        :return: 참여자별 가능 시간 리스트
        :raises MeetingNotFoundError: 일정 조율을 찾을 수 없는 경우
        :raises AccessDeniedError: 접근 권한이 없는 경우
        """
        # 접근 권한 확인
        self.get_meeting_with_access_check(meeting_id)

        participants = crud.get_participants(self.session, meeting_id)
        availability_list = []

        for participant in participants:
            time_slots = crud.get_participant_time_slots(
                self.session,
                participant.id,
            )
            availability_list.append(
                AvailabilityRead(
                    participant=ParticipantRead.model_validate(participant),
                    time_slots=[
                        TimeSlotRead.model_validate(slot) for slot in time_slots
                    ],
                )
            )

        return availability_list

    def get_meeting_result(self, meeting_id: UUID) -> MeetingResultRead:
        """
        공통 가능 시간 분석 결과 조회
        
        모든 참여자의 시간 선택을 집계하여 겹치는 시간대와 인원 수를 계산합니다.
        
        :param meeting_id: 일정 조율 ID
        :return: 공통 가능 시간 분석 결과
        :raises MeetingNotFoundError: 일정 조율을 찾을 수 없는 경우
        :raises AccessDeniedError: 접근 권한이 없는 경우
        """
        # 접근 권한 확인
        meeting, is_shared = self.get_meeting_with_access_check(meeting_id)

        # 요일 기반 날짜 생성
        available_dates = self._generate_available_dates(
            meeting.start_date,
            meeting.end_date,
            meeting.available_days,
        )

        # 시간 슬롯 생성 (time_slot_minutes 단위)
        time_slots = self._generate_time_slots(
            meeting.start_time,
            meeting.end_time,
            meeting.time_slot_minutes,
        )

        # 모든 참여자의 시간 슬롯 조회
        participants = crud.get_participants(self.session, meeting_id)
        availability_grid: dict[str, dict[str, int]] = {}

        # 그리드 초기화
        for date_obj in available_dates:
            date_str = date_obj.isoformat()
            availability_grid[date_str] = {}
            for time_slot in time_slots:
                time_str = time_slot.strftime("%H:%M")
                availability_grid[date_str][time_str] = 0

        # 각 참여자의 시간 슬롯 집계
        for participant in participants:
            participant_slots = crud.get_participant_time_slots(
                self.session,
                participant.id,
            )

            for slot in participant_slots:
                # 슬롯이 포함하는 모든 시간 슬롯에 카운트 증가
                slot_start = slot.start_time
                slot_end = slot.end_time
                date_str = slot.slot_date.isoformat()

                if date_str not in availability_grid:
                    continue

                for time_slot in time_slots:
                    if slot_start <= time_slot < slot_end:
                        time_str = time_slot.strftime("%H:%M")
                        availability_grid[date_str][time_str] += 1

        return MeetingResultRead(
            meeting=MeetingRead.model_validate(meeting),
            availability_grid=availability_grid,
        )

    def _generate_available_dates(
            self,
            start_date: date,
            end_date: date,
            available_days: List[int],
    ) -> List[date]:
        """
        요일 기반 날짜 생성
        
        start_date ~ end_date 범위 내에서 available_days에 해당하는 날짜만 반환합니다.
        
        :param start_date: 시작 날짜
        :param end_date: 종료 날짜
        :param available_days: 요일 리스트 (0-6, 0=월요일)
        :return: 가능한 날짜 리스트
        """
        available_dates = []
        current_date = start_date

        while current_date <= end_date:
            # weekday(): 0=월요일, 6=일요일
            if current_date.weekday() in available_days:
                available_dates.append(current_date)
            current_date += timedelta(days=1)

        return available_dates

    def _generate_time_slots(
            self,
            start_time: time,
            end_time: time,
            slot_minutes: int,
    ) -> List[time]:
        """
        시간 슬롯 생성
        
        start_time ~ end_time 범위를 slot_minutes 단위로 나눕니다.
        
        :param start_time: 시작 시간
        :param end_time: 종료 시간
        :param slot_minutes: 시간 슬롯 단위 (분)
        :return: 시간 슬롯 리스트
        """
        time_slots = []
        
        # time 객체를 분 단위로 변환하여 계산
        start_minutes = start_time.hour * 60 + start_time.minute
        end_minutes = end_time.hour * 60 + end_time.minute
        current_minutes = start_minutes

        while current_minutes < end_minutes:
            hours = current_minutes // 60
            minutes = current_minutes % 60
            time_slots.append(time(hours, minutes))

            # 다음 슬롯으로 이동
            current_minutes += slot_minutes

        return time_slots

    def to_read_dto(
            self,
            meeting: Meeting,
            is_shared: bool = False,
    ) -> MeetingRead:
        """
        Meeting을 MeetingRead DTO로 변환하고 가시성 정보를 채웁니다.
        
        :param meeting: Meeting 모델
        :param is_shared: 공유된 리소스인지 여부
        :return: MeetingRead DTO (가시성 정보 포함)
        """
        meeting_read = MeetingRead.model_validate(meeting)
        meeting_read.owner_id = meeting.owner_id
        meeting_read.is_shared = is_shared

        # 가시성 레벨 조회
        visibility = visibility_crud.get_visibility_by_resource(
            self.session, ResourceType.MEETING, meeting.id
        )
        if visibility:
            meeting_read.visibility_level = visibility.level

        return meeting_read
