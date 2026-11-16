"""미팅의 게스트 호스트 상태 (app/domain/meeting/guest_host.py)"""
from datetime import date, datetime, time, timedelta
from uuid import uuid4

import pytest

from app.domain.guest.host import GuestHostStatus, host_status, unregister_guest_host
from app.domain.meeting import guest_host
from app.domain.meeting.guest_host import MeetingGuestHost, guest_period_end
from app.domain.user.service import UserProfileService
from app.domain.visibility.enums import ResourceType, VisibilityLevel
from app.domain.visibility.service import VisibilityService
from app.models.meeting import Meeting
from tests.conftest import make_user

OWNER = make_user("owner")
FAR_FUTURE = date(2999, 1, 1)


def _meeting(
        session,
        *,
        allow_guests: bool = True,
        level: VisibilityLevel | None = VisibilityLevel.PUBLIC,
        end_date: date = FAR_FUTURE,
        timezone: str = "UTC",
) -> Meeting:
    meeting = Meeting(
        owner_id=OWNER.sub,
        title="회의",
        start_date=end_date - timedelta(days=2),
        end_date=end_date,
        timezone=timezone,
        available_days=[0, 1, 2, 3, 4, 5, 6],
        start_time=time(9),
        end_time=time(18),
        time_slot_minutes=30,
        allow_guests=allow_guests,
    )
    session.add(meeting)
    session.flush()
    if level is not None:
        VisibilityService(session, OWNER).set_visibility(
            ResourceType.MEETING, meeting.id, level,
            allowed_emails=["a@example.com"] if level == VisibilityLevel.ALLOWED_EMAILS else None,
        )
    session.flush()
    return meeting


def _status(session, meeting_id) -> GuestHostStatus:
    return MeetingGuestHost().guest_status(session, meeting_id)


@pytest.fixture
def clock(monkeypatch):
    """guest_host가 읽는 현재 시각(UTC naive)을 정한다"""
    def set_now(now: datetime) -> None:
        monkeypatch.setattr(guest_host, "utc_now_naive", lambda: now)
    return set_now


def test_open_when_public_and_allowed(test_session):
    assert _status(test_session, _meeting(test_session).id) == GuestHostStatus.OPEN


def test_missing_when_meeting_does_not_exist(test_session):
    assert _status(test_session, uuid4()) == GuestHostStatus.MISSING


def test_missing_after_meeting_is_deleted(test_session):
    meeting = _meeting(test_session)
    test_session.delete(meeting)
    test_session.flush()

    assert _status(test_session, meeting.id) == GuestHostStatus.MISSING


def test_closed_when_guests_not_allowed(test_session):
    assert _status(test_session, _meeting(test_session, allow_guests=False).id) == GuestHostStatus.CLOSED


@pytest.mark.parametrize("level", [
    None,
    VisibilityLevel.PRIVATE,
    VisibilityLevel.FRIENDS,
    VisibilityLevel.SELECTED_FRIENDS,
    VisibilityLevel.ALLOWED_EMAILS,
])
def test_closed_when_not_public(test_session, level):
    assert _status(test_session, _meeting(test_session, level=level).id) == GuestHostStatus.CLOSED


def test_closed_while_level_is_changed_away_and_open_when_changed_back(test_session):
    meeting = _meeting(test_session)
    VisibilityService(test_session, OWNER).set_visibility(ResourceType.MEETING, meeting.id, VisibilityLevel.PRIVATE)
    assert _status(test_session, meeting.id) == GuestHostStatus.CLOSED

    VisibilityService(test_session, OWNER).set_visibility(ResourceType.MEETING, meeting.id, VisibilityLevel.PUBLIC)
    assert _status(test_session, meeting.id) == GuestHostStatus.OPEN


def test_closed_while_visibility_setting_is_deleted(test_session):
    meeting = _meeting(test_session)
    VisibilityService(test_session, OWNER).delete_visibility(ResourceType.MEETING, meeting.id)

    assert _status(test_session, meeting.id) == GuestHostStatus.CLOSED


def test_closed_while_owner_is_dormant_and_open_after_cancel(test_session):
    meeting = _meeting(test_session)
    profiles = UserProfileService(test_session, OWNER)

    profiles.request_deletion()
    assert _status(test_session, meeting.id) == GuestHostStatus.CLOSED

    profiles.cancel_deletion()
    assert _status(test_session, meeting.id) == GuestHostStatus.OPEN


class TestGuestPeriod:
    def test_ends_at_midnight_31_days_after_end_date_in_meeting_timezone(self, test_session):
        meeting = _meeting(test_session, end_date=date(2026, 1, 10), timezone="Asia/Seoul")

        # 2026-02-10 00:00 KST
        assert guest_period_end(meeting) == datetime(2026, 2, 9, 15, 0)

    def test_follows_daylight_saving_offset_of_that_day(self, test_session):
        # 2026-03-10 00:00 EDT (일광 절약 시간은 2026-03-08 시작)
        meeting = _meeting(test_session, end_date=date(2026, 2, 7), timezone="America/New_York")

        assert guest_period_end(meeting) == datetime(2026, 3, 10, 4, 0)

    def test_open_just_before_end_and_expired_from_end(self, test_session, clock):
        meeting = _meeting(test_session, end_date=date(2026, 1, 10), timezone="Asia/Seoul")
        end = datetime(2026, 2, 9, 15, 0)

        clock(end - timedelta(microseconds=1))
        assert _status(test_session, meeting.id) == GuestHostStatus.OPEN

        clock(end)
        assert _status(test_session, meeting.id) == GuestHostStatus.EXPIRED

    def test_same_instant_differs_by_meeting_timezone(self, test_session, clock):
        """같은 날 끝나는 미팅도 시간대가 다르면 기간이 끝나는 시각이 다르다"""
        seoul = _meeting(test_session, end_date=date(2026, 1, 10), timezone="Asia/Seoul")
        utc = _meeting(test_session, end_date=date(2026, 1, 10), timezone="UTC")

        clock(datetime(2026, 2, 9, 20, 0))  # 서울은 2026-02-10 05:00, UTC는 2026-02-09 20:00

        assert _status(test_session, seoul.id) == GuestHostStatus.EXPIRED
        assert _status(test_session, utc.id) == GuestHostStatus.OPEN

    @pytest.mark.parametrize("allow_guests, level", [
        (False, VisibilityLevel.PUBLIC),
        (True, VisibilityLevel.PRIVATE),
    ])
    def test_expired_wins_over_closed(self, test_session, clock, allow_guests, level):
        meeting = _meeting(test_session, allow_guests=allow_guests, level=level, end_date=date(2026, 1, 10))

        clock(datetime(2026, 2, 11))

        assert _status(test_session, meeting.id) == GuestHostStatus.EXPIRED

    def test_moving_end_date_later_reopens(self, test_session, clock):
        meeting = _meeting(test_session, end_date=date(2026, 1, 10))
        clock(datetime(2026, 2, 11))
        assert _status(test_session, meeting.id) == GuestHostStatus.EXPIRED

        meeting.end_date = date(2026, 1, 20)
        test_session.flush()

        assert _status(test_session, meeting.id) == GuestHostStatus.OPEN


def test_register_sets_host_for_meeting(test_session):
    meeting = _meeting(test_session)
    guest_host.register()
    try:
        assert host_status(test_session, ResourceType.MEETING, meeting.id) == GuestHostStatus.OPEN
    finally:
        unregister_guest_host(ResourceType.MEETING)
