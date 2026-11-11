"""참여자·가능 시간이 있는 미팅 삭제 (ORM 관계를 미리 불러온 경우 포함)"""
from datetime import date, time

from sqlmodel import select

from app.models.meeting import Meeting, MeetingParticipant, MeetingTimeSlot


def _meeting_with_participant(session) -> Meeting:
    meeting = Meeting(
        owner_id="owner",
        title="회의",
        start_date=date(2024, 2, 1),
        end_date=date(2024, 2, 7),
        available_days=[0, 1, 2, 3, 4],
        start_time=time(9),
        end_time=time(18),
        time_slot_minutes=30,
    )
    session.add(meeting)
    session.flush()
    participant = MeetingParticipant(meeting_id=meeting.id, user_id="member", display_name="참여자")
    session.add(participant)
    session.flush()
    session.add(MeetingTimeSlot(
        participant_id=participant.id,
        slot_date=date(2024, 2, 5),
        start_time=time(9),
        end_time=time(12),
    ))
    session.flush()
    return meeting


def _assert_children_gone(session):
    assert session.exec(select(MeetingParticipant)).all() == []
    assert session.exec(select(MeetingTimeSlot)).all() == []


def test_delete_meeting_without_loading_participants(test_session):
    meeting = _meeting_with_participant(test_session)
    test_session.expire_all()

    test_session.delete(test_session.get(Meeting, meeting.id))
    test_session.flush()

    _assert_children_gone(test_session)


def test_delete_meeting_after_loading_participants_and_slots(test_session):
    meeting = _meeting_with_participant(test_session)
    test_session.expire_all()
    loaded = test_session.get(Meeting, meeting.id)
    assert [len(p.time_slots) for p in loaded.participants] == [1]

    test_session.delete(loaded)
    test_session.flush()

    _assert_children_gone(test_session)


def test_delete_participant_removes_its_slots(test_session):
    _meeting_with_participant(test_session)
    participant = test_session.exec(select(MeetingParticipant)).one()

    test_session.delete(participant)
    test_session.flush()

    assert test_session.exec(select(Meeting)).all() != []
    _assert_children_gone(test_session)
