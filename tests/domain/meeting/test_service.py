"""
MeetingService 테스트

일정 조율 서비스 비즈니스 로직 테스트
"""
from datetime import date, time
from uuid import UUID

import pytest

from app.domain.meeting.exceptions import (
    MeetingNotFoundError,
    MeetingParticipantNotFoundError,
)
from app.domain.visibility.exceptions import AccessDeniedError
from app.domain.meeting.schema.dto import (
    MeetingCreate,
    MeetingUpdate,
    ParticipantCreate,
    TimeSlotCreate,
)
from app.domain.meeting.service import MeetingService
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


class TestCreateMeeting:
    """일정 조율 생성 테스트"""

    def test_create_meeting_success(self, test_session, test_user, meeting_data):
        """일정 조율 생성 성공"""
        service = MeetingService(test_session, test_user)
        meeting = service.create_meeting(meeting_data)

        assert meeting.title == "팀 회의 일정 조율"
        assert meeting.description == "다음 주 회의 일정을 조율합니다"
        assert meeting.start_date == date(2024, 2, 1)
        assert meeting.end_date == date(2024, 2, 7)
        assert meeting.available_days == [0, 2, 4]
        assert meeting.start_time == time(9, 0)
        assert meeting.end_time == time(18, 0)
        assert meeting.time_slot_minutes == 30
        assert meeting.owner_id == test_user.sub
        assert isinstance(meeting.id, UUID)

    def test_create_meeting_with_visibility(
            self, test_session, test_user, meeting_data
    ):
        """가시성 설정과 함께 일정 조율 생성"""
        from app.domain.meeting.schema.dto import VisibilitySettings

        meeting_data.visibility = VisibilitySettings(
            level=VisibilityLevel.ALLOWED_EMAILS,
            allowed_emails=["user@company.com"],
            allowed_domains=["company.com"],
        )

        service = MeetingService(test_session, test_user)
        meeting = service.create_meeting(meeting_data)

        # 가시성 설정 확인
        from app.domain.visibility.service import VisibilityService
        visibility_service = VisibilityService(test_session, test_user)
        visibility = visibility_service.get_visibility(
            ResourceType.MEETING, meeting.id
        )
        assert visibility is not None
        assert visibility.level == VisibilityLevel.ALLOWED_EMAILS
        assert "user@company.com" in visibility.allowed_emails
        assert "company.com" in visibility.allowed_domains


class TestGetMeeting:
    """일정 조율 조회 테스트"""

    def test_get_meeting_success(self, test_session, test_user, sample_meeting):
        """일정 조율 조회 성공"""
        service = MeetingService(test_session, test_user)
        meeting = service.get_meeting(sample_meeting.id)

        assert meeting.id == sample_meeting.id
        assert meeting.title == sample_meeting.title

    def test_get_meeting_not_found(self, test_session, test_user):
        """존재하지 않는 일정 조율 조회"""
        service = MeetingService(test_session, test_user)

        with pytest.raises(MeetingNotFoundError):
            service.get_meeting(UUID("00000000-0000-0000-0000-000000000000"))

    def test_get_meeting_with_access_check_owner(
            self, test_session, test_user, sample_meeting
    ):
        """소유자 접근 확인"""
        service = MeetingService(test_session, test_user)
        meeting, is_shared = service.get_meeting_with_access_check(sample_meeting.id)

        assert meeting.id == sample_meeting.id
        assert is_shared is False

    def test_get_meeting_with_access_check_public(
            self, test_session, test_user, other_user, sample_meeting
    ):
        """PUBLIC 레벨 접근 확인"""
        from app.domain.visibility.service import VisibilityService

        # PUBLIC으로 설정
        visibility_service = VisibilityService(test_session, test_user)
        visibility_service.set_visibility(
            resource_type=ResourceType.MEETING,
            resource_id=sample_meeting.id,
            level=VisibilityLevel.PUBLIC,
        )

        # 다른 사용자 접근
        other_service = MeetingService(test_session, other_user)
        meeting, is_shared = other_service.get_meeting_with_access_check(
            sample_meeting.id
        )

        assert meeting.id == sample_meeting.id
        assert is_shared is True

    def test_get_meeting_with_access_check_allowed_email(
            self, test_session, test_user, other_user, sample_meeting
    ):
        """ALLOWED_EMAILS 레벨 접근 확인"""
        from app.domain.visibility.service import VisibilityService

        # ALLOWED_EMAILS로 설정
        visibility_service = VisibilityService(test_session, test_user)
        visibility_service.set_visibility(
            resource_type=ResourceType.MEETING,
            resource_id=sample_meeting.id,
            level=VisibilityLevel.ALLOWED_EMAILS,
            allowed_emails=[other_user.email],
        )

        # 허용된 이메일 사용자 접근
        other_service = MeetingService(test_session, other_user)
        meeting, is_shared = other_service.get_meeting_with_access_check(
            sample_meeting.id
        )

        assert meeting.id == sample_meeting.id
        assert is_shared is True

    def test_get_meeting_with_access_check_denied(
            self, test_session, test_user, other_user, sample_meeting
    ):
        """접근 거부 확인"""
        # 가시성 설정 없음 (PRIVATE으로 간주)

        # 다른 사용자 접근 시도
        other_service = MeetingService(test_session, other_user)

        with pytest.raises(AccessDeniedError):
            other_service.get_meeting_with_access_check(sample_meeting.id)


class TestUpdateMeeting:
    """일정 조율 업데이트 테스트"""

    def test_update_meeting_success(self, test_session, test_user, sample_meeting):
        """일정 조율 업데이트 성공"""
        service = MeetingService(test_session, test_user)

        update_data = MeetingUpdate(
            title="업데이트된 제목",
            description="업데이트된 설명",
        )

        updated_meeting = service.update_meeting(sample_meeting.id, update_data)

        assert updated_meeting.title == "업데이트된 제목"
        assert updated_meeting.description == "업데이트된 설명"
        assert updated_meeting.start_date == sample_meeting.start_date  # 변경되지 않음

    def test_update_meeting_not_found(self, test_session, test_user):
        """존재하지 않는 일정 조율 업데이트"""
        service = MeetingService(test_session, test_user)

        update_data = MeetingUpdate(title="새 제목")

        with pytest.raises(MeetingNotFoundError):
            service.update_meeting(UUID("00000000-0000-0000-0000-000000000000"), update_data)


class TestDeleteMeeting:
    """일정 조율 삭제 테스트"""

    def test_delete_meeting_success(self, test_session, test_user, sample_meeting):
        """일정 조율 삭제 성공"""
        service = MeetingService(test_session, test_user)
        meeting_id = sample_meeting.id

        service.delete_meeting(meeting_id)

        # 삭제 확인
        with pytest.raises(MeetingNotFoundError):
            service.get_meeting(meeting_id)

    def test_delete_meeting_not_found(self, test_session, test_user):
        """존재하지 않는 일정 조율 삭제"""
        service = MeetingService(test_session, test_user)

        with pytest.raises(MeetingNotFoundError):
            service.delete_meeting(UUID("00000000-0000-0000-0000-000000000000"))


class TestParticipant:
    """참여자 관리 테스트"""

    def test_create_participant_success(
            self, test_session, test_user, sample_meeting
    ):
        """참여자 등록 성공"""
        service = MeetingService(test_session, test_user)

        participant_data = ParticipantCreate(display_name="참여자1")
        participant = service.create_participant(sample_meeting.id, participant_data)

        assert participant.meeting_id == sample_meeting.id
        assert participant.user_id == test_user.sub
        assert participant.display_name == "참여자1"
        assert isinstance(participant.id, UUID)

    def test_get_participants_success(
            self, test_session, test_user, sample_meeting
    ):
        """참여자 목록 조회 성공"""
        service = MeetingService(test_session, test_user)

        # 참여자 2명 등록
        participant1 = service.create_participant(
            sample_meeting.id, ParticipantCreate(display_name="참여자1")
        )
        participant2 = service.create_participant(
            sample_meeting.id, ParticipantCreate(display_name="참여자2")
        )

        participants = service.get_participants(sample_meeting.id)

        assert len(participants) == 2
        participant_ids = {p.id for p in participants}
        assert participant1.id in participant_ids
        assert participant2.id in participant_ids


class TestTimeSlots:
    """시간 슬롯 관리 테스트"""

    def test_set_time_slots_success(
            self, test_session, test_user, sample_meeting
    ):
        """시간 슬롯 설정 성공"""
        service = MeetingService(test_session, test_user)

        # 참여자 등록
        participant = service.create_participant(
            sample_meeting.id, ParticipantCreate(display_name="참여자1")
        )

        # 시간 슬롯 설정
        time_slots = [
            TimeSlotCreate(
                slot_date=date(2024, 2, 1),  # 월요일
                start_time=time(9, 0),
                end_time=time(12, 0),
            ),
            TimeSlotCreate(
                slot_date=date(2024, 2, 1),
                start_time=time(14, 0),
                end_time=time(17, 0),
            ),
        ]

        created_slots = service.set_time_slots(
            sample_meeting.id, participant.id, time_slots
        )

        assert len(created_slots) == 2
        assert created_slots[0].slot_date == date(2024, 2, 1)
        assert created_slots[0].start_time == time(9, 0)
        assert created_slots[0].end_time == time(12, 0)

    def test_set_time_slots_replaces_existing(
            self, test_session, test_user, sample_meeting
    ):
        """시간 슬롯 설정 시 기존 슬롯 교체"""
        service = MeetingService(test_session, test_user)

        # 참여자 등록
        participant = service.create_participant(
            sample_meeting.id, ParticipantCreate(display_name="참여자1")
        )

        # 첫 번째 시간 슬롯 설정
        time_slots1 = [
            TimeSlotCreate(
                slot_date=date(2024, 2, 1),
                start_time=time(9, 0),
                end_time=time(12, 0),
            ),
        ]
        service.set_time_slots(sample_meeting.id, participant.id, time_slots1)

        # 두 번째 시간 슬롯 설정 (기존 슬롯 교체)
        time_slots2 = [
            TimeSlotCreate(
                slot_date=date(2024, 2, 1),
                start_time=time(14, 0),
                end_time=time(17, 0),
            ),
        ]
        created_slots = service.set_time_slots(
            sample_meeting.id, participant.id, time_slots2
        )

        # 기존 슬롯이 교체되어 1개만 남아야 함
        assert len(created_slots) == 1
        assert created_slots[0].start_time == time(14, 0)

    def test_set_time_slots_denies_other_participant(
            self, test_session, test_user, other_user, sample_meeting
    ):
        """다른 참여자의 시간 슬롯 설정 불가"""
        from app.domain.visibility.service import VisibilityService

        # PUBLIC으로 설정하여 other_user 접근 가능하게 함
        visibility_service = VisibilityService(test_session, test_user)
        visibility_service.set_visibility(
            resource_type=ResourceType.MEETING,
            resource_id=sample_meeting.id,
            level=VisibilityLevel.PUBLIC,
        )

        # test_user로 참여자 등록
        owner_service = MeetingService(test_session, test_user)
        participant = owner_service.create_participant(
            sample_meeting.id, ParticipantCreate(display_name="참여자1")
        )

        # other_user로 시간 슬롯 설정 시도
        other_service = MeetingService(test_session, other_user)

        with pytest.raises(AccessDeniedError):
            other_service.set_time_slots(
                sample_meeting.id,
                participant.id,
                [TimeSlotCreate(
                    slot_date=date(2024, 2, 1),
                    start_time=time(9, 0),
                    end_time=time(12, 0),
                )],
            )


class TestMeetingResult:
    """공통 가능 시간 분석 테스트"""

    def test_get_meeting_result_success(
            self, test_session, test_user, sample_meeting
    ):
        """공통 가능 시간 분석 성공"""
        service = MeetingService(test_session, test_user)

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
        result = service.get_meeting_result(sample_meeting.id)

        assert result.meeting.id == sample_meeting.id
        assert "2024-02-02" in result.availability_grid

        # 10:00-12:00 구간은 두 명 모두 가능 (count=2)
        date_grid = result.availability_grid["2024-02-02"]
        assert date_grid.get("10:00", 0) == 2
        assert date_grid.get("11:00", 0) == 2
        assert date_grid.get("11:30", 0) == 2

        # 9:00-10:00 구간은 참여자1만 가능 (count=1)
        assert date_grid.get("09:00", 0) == 1
        assert date_grid.get("09:30", 0) == 1

    def test_generate_available_dates(self, test_session, test_user):
        """요일 기반 날짜 생성 테스트"""
        service = MeetingService(test_session, test_user)

        # 월, 수, 금만 가능
        available_dates = service._generate_available_dates(
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
        service = MeetingService(test_session, test_user)

        time_slots = service._generate_time_slots(
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
