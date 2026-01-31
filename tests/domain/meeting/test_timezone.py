"""
Meeting Timezone 테스트

Meeting DTO의 타임존 변환 로직 검증:
- MeetingRead.to_timezone() 테스트
- ParticipantRead.to_timezone() 테스트
- UTC → Asia/Seoul 변환 테스트
- UTC → UTC offset (+09:00) 변환 테스트
- None 전달 시 원본 반환 테스트
"""
from datetime import date, datetime, time, timezone, timedelta
from uuid import uuid4

import pytest

from app.domain.dateutil.exceptions import InvalidTimezoneError
from app.domain.meeting.schema.dto import MeetingRead, ParticipantRead


class TestMeetingReadTimezone:
    """MeetingRead.to_timezone() 메서드 테스트"""

    def test_to_timezone_none_returns_self(self):
        """타임존이 None인 경우 원본 반환"""
        meeting_read = MeetingRead(
            id=uuid4(),
            owner_id="user123",
            title="테스트 미팅",
            start_date=date(2024, 2, 1),
            end_date=date(2024, 2, 7),
            available_days=[0, 2, 4],
            start_time=time(9, 0),
            end_time=time(18, 0),
            time_slot_minutes=30,
            created_at=datetime(2024, 1, 1, 10, 0, 0),
            updated_at=datetime(2024, 1, 1, 10, 0, 0),
        )

        result = meeting_read.to_timezone(None)

        assert result is meeting_read  # 같은 객체 반환
        assert result.created_at == datetime(2024, 1, 1, 10, 0, 0)

    def test_to_timezone_utc_timezone_object(self):
        """UTC timezone 객체로 변환"""
        meeting_read = MeetingRead(
            id=uuid4(),
            owner_id="user123",
            title="테스트 미팅",
            start_date=date(2024, 2, 1),
            end_date=date(2024, 2, 7),
            available_days=[0, 2, 4],
            start_time=time(9, 0),
            end_time=time(18, 0),
            time_slot_minutes=30,
            created_at=datetime(2024, 1, 1, 10, 0, 0),
            updated_at=datetime(2024, 1, 1, 10, 0, 0),
        )

        result = meeting_read.to_timezone(timezone.utc)

        assert result.created_at.tzinfo == timezone.utc
        assert result.updated_at.tzinfo == timezone.utc
        assert result.created_at == datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        # date와 time 필드는 변환되지 않음
        assert result.start_date == date(2024, 2, 1)
        assert result.start_time == time(9, 0)

    def test_to_timezone_kst_offset_string(self):
        """KST UTC offset 문자열로 변환 (+09:00)"""
        meeting_read = MeetingRead(
            id=uuid4(),
            owner_id="user123",
            title="테스트 미팅",
            start_date=date(2024, 2, 1),
            end_date=date(2024, 2, 7),
            available_days=[0, 2, 4],
            start_time=time(9, 0),
            end_time=time(18, 0),
            time_slot_minutes=30,
            created_at=datetime(2024, 1, 1, 10, 0, 0),  # UTC 10:00
            updated_at=datetime(2024, 1, 1, 11, 0, 0),  # UTC 11:00
        )

        result = meeting_read.to_timezone("+09:00")

        # UTC 10:00 -> KST 19:00
        assert result.created_at.hour == 19
        assert result.created_at.tzinfo is not None
        # UTC 11:00 -> KST 20:00
        assert result.updated_at.hour == 20
        assert result.updated_at.tzinfo is not None
        # date와 time 필드는 변환되지 않음
        assert result.start_date == date(2024, 2, 1)
        assert result.start_time == time(9, 0)

    def test_to_timezone_asia_seoul_string(self):
        """Asia/Seoul 타임존 이름으로 변환"""
        try:
            from zoneinfo import ZoneInfo
            meeting_read = MeetingRead(
                id=uuid4(),
                owner_id="user123",
                title="테스트 미팅",
                start_date=date(2024, 2, 1),
                end_date=date(2024, 2, 7),
                available_days=[0, 2, 4],
                start_time=time(9, 0),
                end_time=time(18, 0),
                time_slot_minutes=30,
                created_at=datetime(2024, 1, 1, 10, 0, 0),  # UTC 10:00
                updated_at=datetime(2024, 1, 1, 11, 0, 0),  # UTC 11:00
            )

            try:
                result = meeting_read.to_timezone("Asia/Seoul")

                # UTC 10:00 -> KST 19:00
                assert result.created_at.hour == 19
                assert isinstance(result.created_at.tzinfo, ZoneInfo)
                assert str(result.created_at.tzinfo) == "Asia/Seoul"
            except InvalidTimezoneError:
                pytest.skip("tzdata package not installed or timezone not found")
        except ImportError:
            pytest.skip("zoneinfo not available")

    def test_to_timezone_preserves_other_fields(self):
        """타임존 변환 시 다른 필드가 보존되는지 확인"""
        meeting_read = MeetingRead(
            id=uuid4(),
            owner_id="user123",
            title="테스트 미팅",
            description="설명",
            start_date=date(2024, 2, 1),
            end_date=date(2024, 2, 7),
            available_days=[0, 2, 4],
            start_time=time(9, 0),
            end_time=time(18, 0),
            time_slot_minutes=30,
            created_at=datetime(2024, 1, 1, 10, 0, 0),
            updated_at=datetime(2024, 1, 1, 11, 0, 0),
            visibility_level=None,
            is_shared=False,
        )

        result = meeting_read.to_timezone("+09:00")

        # 모든 필드가 보존되어야 함
        assert result.id == meeting_read.id
        assert result.owner_id == meeting_read.owner_id
        assert result.title == meeting_read.title
        assert result.description == meeting_read.description
        assert result.start_date == meeting_read.start_date
        assert result.end_date == meeting_read.end_date
        assert result.available_days == meeting_read.available_days
        assert result.start_time == meeting_read.start_time
        assert result.end_time == meeting_read.end_time
        assert result.time_slot_minutes == meeting_read.time_slot_minutes
        assert result.visibility_level == meeting_read.visibility_level
        assert result.is_shared == meeting_read.is_shared

    def test_to_timezone_with_date_crossing(self):
        """날짜 경계를 넘는 타임존 변환"""
        # UTC 23:00을 KST로 변환하면 다음날 08:00
        meeting_read = MeetingRead(
            id=uuid4(),
            owner_id="user123",
            title="테스트 미팅",
            start_date=date(2024, 2, 1),
            end_date=date(2024, 2, 7),
            available_days=[0, 2, 4],
            start_time=time(9, 0),
            end_time=time(18, 0),
            time_slot_minutes=30,
            created_at=datetime(2024, 1, 1, 23, 0, 0),  # UTC 23:00
            updated_at=datetime(2024, 1, 1, 23, 0, 0),
        )

        result = meeting_read.to_timezone("+09:00")

        # UTC 23:00 -> KST 08:00 (다음날)
        assert result.created_at.hour == 8
        assert result.created_at.day == 2  # 다음날


class TestParticipantReadTimezone:
    """ParticipantRead.to_timezone() 메서드 테스트"""

    def test_to_timezone_none_returns_self(self):
        """타임존이 None인 경우 원본 반환"""
        participant_read = ParticipantRead(
            id=uuid4(),
            meeting_id=uuid4(),
            user_id="user123",
            display_name="참여자1",
            created_at=datetime(2024, 1, 1, 10, 0, 0),
        )

        result = participant_read.to_timezone(None)

        assert result is participant_read  # 같은 객체 반환

    def test_to_timezone_kst_offset_string(self):
        """KST UTC offset 문자열로 변환 (+09:00)"""
        participant_read = ParticipantRead(
            id=uuid4(),
            meeting_id=uuid4(),
            user_id="user123",
            display_name="참여자1",
            created_at=datetime(2024, 1, 1, 10, 0, 0),  # UTC 10:00
        )

        result = participant_read.to_timezone("+09:00")

        # UTC 10:00 -> KST 19:00
        assert result.created_at.hour == 19
        assert result.created_at.tzinfo is not None
        # 다른 필드는 보존
        assert result.id == participant_read.id
        assert result.display_name == participant_read.display_name

    def test_to_timezone_preserves_other_fields(self):
        """타임존 변환 시 다른 필드가 보존되는지 확인"""
        participant_read = ParticipantRead(
            id=uuid4(),
            meeting_id=uuid4(),
            user_id="user123",
            display_name="참여자1",
            created_at=datetime(2024, 1, 1, 10, 0, 0),
        )

        result = participant_read.to_timezone("+09:00")

        # 모든 필드가 보존되어야 함
        assert result.id == participant_read.id
        assert result.meeting_id == participant_read.meeting_id
        assert result.user_id == participant_read.user_id
        assert result.display_name == participant_read.display_name
