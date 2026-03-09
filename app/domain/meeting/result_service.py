"""
Meeting Result Service

공통 가능 시간 분석 비즈니스 로직
"""
from datetime import date, time, timedelta
from typing import List
from uuid import UUID

from sqlmodel import Session

from app.core.auth import CurrentUser
from app.crud import meeting as crud
from app.domain.meeting.schema.dto import (
    MeetingRead,
    ParticipantRead,
    TimeSlotRead,
    AvailabilityRead,
    AvailabilityTimeSlot,
    AvailabilityDateGroup,
    MeetingResultRead,
)
from app.domain.meeting.service import MeetingService


class MeetingResultService:
    """
    Meeting Result Service - 가용시간 분석 비즈니스 로직

    참여자별 가능 시간 조회 및 공통 가능 시간 분석을 담당합니다.
    """

    def __init__(self, session: Session, current_user: CurrentUser):
        self.session = session
        self.current_user = current_user
        self._meeting_service = MeetingService(session, current_user)

    def get_availability(self, meeting_id: UUID) -> List[AvailabilityRead]:
        """
        전체 참여자의 가능 시간 조회

        :param meeting_id: 일정 조율 ID
        :return: 참여자별 가능 시간 리스트
        :raises MeetingNotFoundError: 일정 조율을 찾을 수 없는 경우
        :raises AccessDeniedError: 접근 권한이 없는 경우
        """
        # 접근 권한 확인
        self._meeting_service.get_meeting_with_access_check(meeting_id)

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
        meeting, is_shared = self._meeting_service.get_meeting_with_access_check(meeting_id)

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

        # 그리드 초기화
        counts: dict[str, dict[str, int]] = {}
        for date_obj in available_dates:
            date_str = date_obj.isoformat()
            counts[date_str] = {}
            for time_slot in time_slots:
                time_str = time_slot.strftime("%H:%M")
                counts[date_str][time_str] = 0

        # 모든 참여자의 시간 슬롯을 JOIN 한 번으로 조회 (N+1 제거)
        all_slots = crud.get_time_slots_by_meeting(self.session, meeting_id)

        # 인덱스 직접 계산으로 집계 (불필요한 순회 제거)
        grid_start_minutes = meeting.start_time.hour * 60 + meeting.start_time.minute
        slot_minutes = meeting.time_slot_minutes

        for slot in all_slots:
            date_str = slot.slot_date.isoformat()
            if date_str not in counts:
                continue

            slot_start_minutes = slot.start_time.hour * 60 + slot.start_time.minute
            slot_end_minutes = slot.end_time.hour * 60 + slot.end_time.minute

            start_idx = (slot_start_minutes - grid_start_minutes) // slot_minutes
            end_idx = (slot_end_minutes - grid_start_minutes) // slot_minutes

            # 그리드 범위 내로 클램핑
            start_idx = max(0, start_idx)
            end_idx = min(len(time_slots), end_idx)

            for i in range(start_idx, end_idx):
                time_str = time_slots[i].strftime("%H:%M")
                counts[date_str][time_str] += 1

        availability_grid = [
            AvailabilityDateGroup(
                date=date_str,
                slots=[
                    AvailabilityTimeSlot(time=time_str, count=count)
                    for time_str, count in time_map.items()
                ],
            )
            for date_str, time_map in counts.items()
        ]

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
