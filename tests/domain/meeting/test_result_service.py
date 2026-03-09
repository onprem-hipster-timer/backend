"""
MeetingResultService 테스트

공통 가능 시간 분석 비즈니스 로직 테스트
"""
from datetime import date, time
from uuid import UUID

import pytest

from app.domain.meeting.schema.dto import (
    MeetingCreate,
    ParticipantCreate,
    TimeSlotCreate,
)
from app.domain.meeting.service import MeetingService
from app.domain.meeting.result_service import MeetingResultService
from app.domain.visibility.enums import VisibilityLevel, ResourceType


@pytest.fixture
def meeting_data() -> MeetingCreate:
    """테스트용 일정 조율 데이터"""
    return MeetingCreate(
        title="팀 회의 일정 조율",
        description="다음 주 회의 일정을 조율합니다",
        start_date=date(2024, 2, 1),
        end_date=date(2024, 2, 7),
        available_days=[0, 2, 4],  # 월, 수, 금
        start_time=time(9, 0),
        end_time=time(18, 0),
        time_slot_minutes=30,
    )


@pytest.fixture
def sample_meeting(test_session, test_user, meeting_data):
    """테스트용 일정 조율"""
    service = MeetingService(test_session, test_user)
    meeting = service.create_meeting(meeting_data)
    test_session.flush()
    test_session.refresh(meeting)
    return meeting


class TestMeetingResult:
    """공통 가능 시간 분석 테스트"""

    def test_get_meeting_result_success(
            self, test_session, test_user, sample_meeting
    ):
        """공통 가능 시간 분석 성공"""
        service = MeetingService(test_session, test_user)
        result_service = MeetingResultService(test_session, test_user)

        # 참여자 2명 등록
        participant1 = service.create_participant(
            sample_meeting.id, ParticipantCreate(display_name="참여자1")
        )
        participant2 = service.create_participant(
            sample_meeting.id, ParticipantCreate(display_name="참여자2")
        )

        # 참여자1: 2월 2일(금) 9:00-12:00 가능
        service.set_time_slots(
            sample_meeting.id,
            participant1.id,
            [TimeSlotCreate(
                slot_date=date(2024, 2, 2),  # 금요일 (weekday=4, available_days에 포함)
                start_time=time(9, 0),
                end_time=time(12, 0),
            )],
        )

        # 참여자2: 2월 2일(금) 10:00-13:00 가능
        service.set_time_slots(
            sample_meeting.id,
            participant2.id,
            [TimeSlotCreate(
                slot_date=date(2024, 2, 2),  # 금요일 (weekday=4, available_days에 포함)
                start_time=time(10, 0),
                end_time=time(13, 0),
            )],
        )

        # 공통 가능 시간 분석
        result = result_service.get_meeting_result(sample_meeting.id)

        assert result.meeting.id == sample_meeting.id

        date_group = next((g for g in result.availability_grid if g.date == "2024-02-02"), None)
        assert date_group is not None

        slots = {s.time: s.count for s in date_group.slots}

        # 10:00-12:00 구간은 두 명 모두 가능 (count=2)
        assert slots.get("10:00", 0) == 2
        assert slots.get("11:00", 0) == 2
        assert slots.get("11:30", 0) == 2

        # 9:00-10:00 구간은 참여자1만 가능 (count=1)
        assert slots.get("09:00", 0) == 1
        assert slots.get("09:30", 0) == 1

    def test_generate_available_dates(self, test_session, test_user):
        """요일 기반 날짜 생성 테스트"""
        result_service = MeetingResultService(test_session, test_user)

        # 월, 수, 금만 가능
        available_dates = result_service._generate_available_dates(
            start_date=date(2024, 2, 1),  # 목요일
            end_date=date(2024, 2, 7),  # 수요일
            available_days=[0, 2, 4],  # 월, 수, 금
        )

        # 2월 1일(목) ~ 2월 7일(수) 중 월, 수, 금만 포함
        # 2월 2일(금), 2월 5일(월), 2월 7일(수)
        assert len(available_dates) == 3
        assert date(2024, 2, 2) in available_dates  # 금요일
        assert date(2024, 2, 5) in available_dates  # 월요일
        assert date(2024, 2, 7) in available_dates  # 수요일

    def test_generate_time_slots(self, test_session, test_user):
        """시간 슬롯 생성 테스트"""
        result_service = MeetingResultService(test_session, test_user)

        time_slots = result_service._generate_time_slots(
            start_time=time(9, 0),
            end_time=time(12, 0),
            slot_minutes=30,
        )

        # 9:00 ~ 12:00를 30분 단위로 나눔
        # 9:00, 9:30, 10:00, 10:30, 11:00, 11:30 (12:00은 제외)
        assert len(time_slots) == 6
        assert time_slots[0] == time(9, 0)
        assert time_slots[1] == time(9, 30)
        assert time_slots[2] == time(10, 0)
        assert time_slots[-1] == time(11, 30)

    def test_get_meeting_result_no_participants(
            self, test_session, test_user, sample_meeting
    ):
        """참여자 없는 미팅의 결과 분석 - 모든 카운트 0"""
        result_service = MeetingResultService(test_session, test_user)
        result = result_service.get_meeting_result(sample_meeting.id)

        assert result.meeting.id == sample_meeting.id
        for date_group in result.availability_grid:
            for slot in date_group.slots:
                assert slot.count == 0

    def test_get_meeting_result_slot_outside_grid_ignored(
            self, test_session, test_user
    ):
        """그리드 범위 밖의 참여자 슬롯은 무시"""
        service = MeetingService(test_session, test_user)
        result_service = MeetingResultService(test_session, test_user)

        # 10:00~12:00 그리드의 미팅 생성
        meeting = service.create_meeting(MeetingCreate(
            title="범위 테스트",
            start_date=date(2024, 2, 5),  # 월요일
            end_date=date(2024, 2, 5),
            available_days=[0],
            start_time=time(10, 0),
            end_time=time(12, 0),
            time_slot_minutes=30,
        ))

        participant = service.create_participant(
            meeting.id, ParticipantCreate(display_name="참여자")
        )

        # 그리드 범위 밖 슬롯 설정 (08:00~09:00)
        service.set_time_slots(
            meeting.id,
            participant.id,
            [TimeSlotCreate(
                slot_date=date(2024, 2, 5),
                start_time=time(8, 0),
                end_time=time(9, 0),
            )],
        )

        result = result_service.get_meeting_result(meeting.id)
        date_group = next(g for g in result.availability_grid if g.date == "2024-02-05")

        # 그리드 범위 밖이므로 모든 카운트 0
        for slot in date_group.slots:
            assert slot.count == 0

    def test_get_meeting_result_slot_partially_overlaps_grid(
            self, test_session, test_user
    ):
        """그리드와 부분 겹침 - 겹치는 부분만 카운트"""
        service = MeetingService(test_session, test_user)
        result_service = MeetingResultService(test_session, test_user)

        # 10:00~12:00 그리드
        meeting = service.create_meeting(MeetingCreate(
            title="부분 겹침",
            start_date=date(2024, 2, 5),
            end_date=date(2024, 2, 5),
            available_days=[0],
            start_time=time(10, 0),
            end_time=time(12, 0),
            time_slot_minutes=30,
        ))

        participant = service.create_participant(
            meeting.id, ParticipantCreate(display_name="참여자")
        )

        # 09:00~11:00 슬롯 (그리드 10:00~12:00과 10:00~11:00 구간만 겹침)
        service.set_time_slots(
            meeting.id,
            participant.id,
            [TimeSlotCreate(
                slot_date=date(2024, 2, 5),
                start_time=time(9, 0),
                end_time=time(11, 0),
            )],
        )

        result = result_service.get_meeting_result(meeting.id)
        date_group = next(g for g in result.availability_grid if g.date == "2024-02-05")
        slots = {s.time: s.count for s in date_group.slots}

        # 10:00, 10:30만 카운트됨
        assert slots["10:00"] == 1
        assert slots["10:30"] == 1
        # 11:00 이후는 0
        assert slots["11:00"] == 0
        assert slots["11:30"] == 0

    def test_get_meeting_result_many_participants(
            self, test_session, test_user, other_user
    ):
        """다수 참여자 정확한 집계 확인"""
        from app.domain.visibility.service import VisibilityService

        service = MeetingService(test_session, test_user)
        result_service = MeetingResultService(test_session, test_user)

        meeting = service.create_meeting(MeetingCreate(
            title="다수 참여자",
            start_date=date(2024, 2, 5),
            end_date=date(2024, 2, 5),
            available_days=[0],
            start_time=time(9, 0),
            end_time=time(12, 0),
            time_slot_minutes=60,
        ))

        # PUBLIC으로 설정
        visibility_service = VisibilityService(test_session, test_user)
        visibility_service.set_visibility(
            resource_type=ResourceType.MEETING,
            resource_id=meeting.id,
            level=VisibilityLevel.PUBLIC,
        )

        # 참여자1 (test_user): 09:00~11:00
        p1 = service.create_participant(
            meeting.id, ParticipantCreate(display_name="참여자1")
        )
        service.set_time_slots(meeting.id, p1.id, [
            TimeSlotCreate(slot_date=date(2024, 2, 5), start_time=time(9, 0), end_time=time(11, 0)),
        ])

        # 참여자2 (other_user): 10:00~12:00
        other_service = MeetingService(test_session, other_user)
        p2 = other_service.create_participant(
            meeting.id, ParticipantCreate(display_name="참여자2")
        )
        other_service.set_time_slots(meeting.id, p2.id, [
            TimeSlotCreate(slot_date=date(2024, 2, 5), start_time=time(10, 0), end_time=time(12, 0)),
        ])

        result = result_service.get_meeting_result(meeting.id)
        date_group = next(g for g in result.availability_grid if g.date == "2024-02-05")
        slots = {s.time: s.count for s in date_group.slots}

        assert slots["09:00"] == 1  # p1만
        assert slots["10:00"] == 2  # p1 + p2
        assert slots["11:00"] == 1  # p2만

    def test_get_meeting_result_non_available_day_slot_ignored(
            self, test_session, test_user
    ):
        """available_days에 없는 날짜의 슬롯은 무시"""
        service = MeetingService(test_session, test_user)
        result_service = MeetingResultService(test_session, test_user)

        # 월요일(0)만 허용
        meeting = service.create_meeting(MeetingCreate(
            title="요일 필터",
            start_date=date(2024, 2, 5),  # 월요일
            end_date=date(2024, 2, 9),    # 금요일
            available_days=[0],            # 월요일만
            start_time=time(9, 0),
            end_time=time(10, 0),
            time_slot_minutes=30,
        ))

        participant = service.create_participant(
            meeting.id, ParticipantCreate(display_name="참여자")
        )

        # 화요일(available_days에 없음)에 슬롯 설정
        service.set_time_slots(meeting.id, participant.id, [
            TimeSlotCreate(
                slot_date=date(2024, 2, 6),  # 화요일
                start_time=time(9, 0),
                end_time=time(10, 0),
            ),
        ])

        result = result_service.get_meeting_result(meeting.id)

        # 월요일만 그리드에 존재
        assert len(result.availability_grid) == 1
        assert result.availability_grid[0].date == "2024-02-05"

        # 화요일 슬롯은 그리드에 없으므로 무시됨, 월요일 카운트 0
        for slot in result.availability_grid[0].slots:
            assert slot.count == 0
