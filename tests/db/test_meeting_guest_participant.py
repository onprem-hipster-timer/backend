"""게스트 참여자 (meeting_participant.guest_id)

게스트 행을 지우면 DB가 그 게스트의 참여자와 가능 시간을 지운다. 회원 참여자와 다른 참여자는 남는다.
"""
from datetime import date, datetime, time

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.domain.guest.model import Guest
from app.models.meeting import Meeting, MeetingParticipant, MeetingTimeSlot
from app.models.visibility import ResourceType


def _meeting(session) -> Meeting:
    meeting = Meeting(
        owner_id="owner",
        title="회의",
        start_date=date(2024, 2, 1),
        end_date=date(2024, 2, 7),
        timezone="UTC",
        mode="hourly",
        available_days=[0, 1, 2, 3, 4],
        start_time=time(9),
        end_time=time(18),
        time_slot_minutes=30,
    )
    session.add(meeting)
    session.flush()
    return meeting


def _guest(session, meeting: Meeting, name: str) -> Guest:
    guest = Guest(identity_id=f"identity-{name}", resource_type=ResourceType.MEETING, resource_id=meeting.id, name=name)
    session.add(guest)
    session.flush()
    return guest


def _participant(session, meeting: Meeting, *, user_id=None, guest: Guest | None = None) -> MeetingParticipant:
    participant = MeetingParticipant(
        meeting_id=meeting.id,
        user_id=user_id,
        guest_id=guest.id if guest else None,
        display_name=guest.name if guest else "회원",
    )
    session.add(participant)
    session.flush()
    session.add(MeetingTimeSlot(
        participant_id=participant.id,
        start_time=datetime(2024, 2, 5, 9),
        end_time=datetime(2024, 2, 5, 12),
    ))
    session.flush()
    return participant


@pytest.fixture
def rows(test_session):
    meeting = _meeting(test_session)
    first, second = _guest(test_session, meeting, "민수"), _guest(test_session, meeting, "지수")
    kept = {
        _participant(test_session, meeting, user_id="member").id,
        _participant(test_session, meeting, guest=second).id,
    }
    _participant(test_session, meeting, guest=first)
    test_session.expire_all()
    return first.id, kept


def _remaining(session) -> tuple[set, set]:
    participants = set(session.exec(select(MeetingParticipant.id)).all())
    slot_owners = set(session.exec(select(MeetingTimeSlot.participant_id)).all())
    return participants, slot_owners


def test_deleting_guest_row_removes_its_participant_and_slots(test_session, rows):
    guest_id, kept = rows

    test_session.delete(test_session.get(Guest, guest_id))
    test_session.flush()
    test_session.expire_all()

    assert _remaining(test_session) == (kept, kept)


def test_bulk_delete_of_guest_rows_removes_their_participants(test_session, rows):
    guest_id, kept = rows

    test_session.execute(delete(Guest).where(Guest.id == guest_id))
    test_session.expire_all()

    assert _remaining(test_session) == (kept, kept)


def test_participant_cannot_be_member_and_guest(test_session):
    meeting = _meeting(test_session)
    guest = _guest(test_session, meeting, "민수")

    with pytest.raises(IntegrityError):
        _participant(test_session, meeting, user_id="member", guest=guest)


def test_one_participant_per_guest(test_session):
    meeting = _meeting(test_session)
    guest = _guest(test_session, meeting, "민수")
    _participant(test_session, meeting, guest=guest)

    with pytest.raises(IntegrityError):
        _participant(test_session, meeting, guest=guest)


def test_participants_without_user_or_guest_are_allowed(test_session):
    """예전 행처럼 user_id와 guest_id가 모두 없는 참여자"""
    meeting = _meeting(test_session)

    _participant(test_session, meeting)
    _participant(test_session, meeting)

    assert len(test_session.exec(select(MeetingParticipant)).all()) == 2
