"""
Meeting Result Service

공통 가능 시간 분석 비즈니스 로직
"""
from bisect import bisect_left
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import List
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlmodel import Session

from app.core.auth import CurrentUser
from app.crud import meeting as crud
from app.domain.dateutil.service import ensure_utc_naive
from app.domain.meeting.schema.dto import (
    MeetingRead,
    ParticipantRead,
    TimeSlotRead,
    AvailabilityRead,
    AvailabilityCell,
    MeetingResultRead,
)
from app.domain.meeting.service import MeetingService
from app.models.meeting import Meeting


class MeetingResultService:
    """
    Meeting Result Service - 가용시간 분석 비즈니스 로직

    참여자별 가능 시간 조회 및 공통 가능 시간 분석을 담당합니다.
    """

    def __init__(self, session: Session, current_user: CurrentUser | None = None):
        """current_user가 없으면 접근을 확인한 미팅을 받는 availability_of·result_of만 쓴다"""
        self.session = session
        self.current_user = current_user
        self._meeting_service = MeetingService(session, current_user) if current_user is not None else None

    def get_availability(self, meeting_id: UUID) -> List[AvailabilityRead]:
        """
        전체 참여자의 가능 시간 조회

        :param meeting_id: 일정 조율 ID
        :return: 참여자별 가능 시간 리스트
        :raises MeetingNotFoundError: 일정 조율이 없거나 접근할 수 없는 경우
        """
        # 접근 권한 확인
        meeting, _ = self._meeting_service.get_meeting_with_access_check(meeting_id)
        return self.availability_of(meeting)

    def availability_of(self, meeting: Meeting, *, hide_user_ids: bool = False) -> List[AvailabilityRead]:
        """미팅의 참여자별 가능 시간 (휴면 회원 제외). hide_user_ids면 참여자의 user_id를 비운다"""
        participants = crud.get_participants(self.session, meeting.id)
        availability_list = []

        for participant in participants:
            time_slots = crud.get_participant_time_slots(
                self.session,
                participant.id,
            )
            participant_read = ParticipantRead.model_validate(participant)
            if hide_user_ids:
                participant_read.user_id = None
            availability_list.append(
                AvailabilityRead(
                    participant=participant_read,
                    time_slots=[
                        TimeSlotRead.model_validate(slot) for slot in time_slots
                    ],
                )
            )

        return availability_list

    def get_meeting_result(self, meeting_id: UUID) -> MeetingResultRead:
        """
        공통 가능 시간 분석 결과 조회

        미팅의 시간대에서 날짜·요일·하루 범위·시간 단위로 칸을 만들고, 칸마다 그 칸을 모두 덮는
        가능 시간을 가진 참여자 수를 셉니다. 한 참여자의 슬롯은 합친 구간으로 봅니다.

        :param meeting_id: 일정 조율 ID
        :return: 공통 가능 시간 분석 결과
        :raises MeetingNotFoundError: 일정 조율이 없거나 접근할 수 없는 경우
        """
        # 접근 권한 확인
        meeting, _ = self._meeting_service.get_meeting_with_access_check(meeting_id)
        return self.result_of(meeting, MeetingRead.model_validate(meeting))

    def result_of(self, meeting: Meeting, meeting_read: MeetingRead) -> MeetingResultRead:
        """미팅의 결과 그리드. 응답의 meeting은 meeting_read"""
        cells = self._generate_cells(meeting)
        cell_starts = [start for start, _ in cells]
        counts = [0] * len(cells)

        # 모든 참여자의 시간 슬롯을 JOIN 한 번으로 조회 (N+1 제거)
        intervals_by_participant: dict[UUID, list[tuple[datetime, datetime]]] = defaultdict(list)
        for slot in crud.get_time_slots_by_meeting(self.session, meeting.id):
            intervals_by_participant[slot.participant_id].append((slot.start_time, slot.end_time))

        # 합친 구간은 서로 겹치지 않으므로 참여자는 칸마다 많아야 한 번 센다
        for intervals in intervals_by_participant.values():
            for start, end in self._merge_intervals(intervals):
                i = bisect_left(cell_starts, start)
                while i < len(cells) and cells[i][1] <= end:
                    counts[i] += 1
                    i += 1

        return MeetingResultRead(
            meeting=meeting_read,
            availability_grid=[
                AvailabilityCell(start_time=start, end_time=end, count=count)
                for (start, end), count in zip(cells, counts)
            ],
        )

    def _generate_cells(self, meeting: Meeting) -> List[tuple[datetime, datetime]]:
        """
        결과 그리드의 칸 [start, end) (UTC naive, 시작 순)

        날마다 미팅 시간대의 start_time~end_time(00:00이면 다음 날 00:00)을 UTC 시각으로 바꾸고,
        그 사이를 실제 경과 시간 time_slot_minutes마다 나눕니다. 일광 절약 시간 전환이 있는 날도
        칸은 이어지는 실제 시각이고, 마지막 칸은 하루 범위의 끝에서 자릅니다.
        """
        zone = ZoneInfo(meeting.timezone)
        step = timedelta(minutes=meeting.time_slot_minutes)
        cells = []
        for day in self._generate_available_dates(
                meeting.start_date, meeting.end_date, meeting.available_days,
        ):
            end_day = day + timedelta(days=1) if meeting.end_time == time(0) else day
            current = ensure_utc_naive(datetime.combine(day, meeting.start_time, zone))
            day_end = ensure_utc_naive(datetime.combine(end_day, meeting.end_time, zone))
            while current < day_end:
                cell_end = min(current + step, day_end)
                cells.append((current, cell_end))
                current = cell_end
        return cells

    @staticmethod
    def _merge_intervals(
            intervals: List[tuple[datetime, datetime]],
    ) -> List[tuple[datetime, datetime]]:
        """겹치거나 맞닿은 반열린 구간을 합친다"""
        merged: List[tuple[datetime, datetime]] = []
        for start, end in sorted(intervals):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        return merged

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
