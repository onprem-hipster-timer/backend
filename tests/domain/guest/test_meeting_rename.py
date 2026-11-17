"""게스트가 이름을 바꾸면 그 게스트의 미팅 참여자 표시 이름도 바뀐다 (app/domain/meeting/event_handlers.py)"""
from datetime import date, time

import pytest
from sqlmodel import select

from app.db.session import _session_manager
from app.domain.guest import service
from app.domain.visibility.enums import ResourceType, VisibilityLevel
from app.domain.visibility.service import VisibilityService
from app.models.meeting import Meeting, MeetingParticipant
from tests.conftest import make_user
from tests.domain.guest.helpers import make_guest

pytestmark = pytest.mark.usefixtures("guest_db", "meeting_host")

OWNER = make_user("owner")


def _open_meeting():
    with _session_manager.get_session() as session:
        meeting = Meeting(
            owner_id=OWNER.sub,
            title="회의",
            start_date=date(2999, 1, 1),
            end_date=date(2999, 1, 3),
            timezone="UTC",
            mode="hourly",
            available_days=[0, 1, 2, 3, 4, 5, 6],
            start_time=time(9),
            end_time=time(18),
            time_slot_minutes=30,
            allow_guests=True,
        )
        session.add(meeting)
        session.flush()
        VisibilityService(session, OWNER).set_visibility(ResourceType.MEETING, meeting.id, VisibilityLevel.PUBLIC)
        session.commit()
        return meeting.id


def _add_participant(meeting_id, display_name: str, *, user_id=None, guest_id=None) -> None:
    with _session_manager.get_session() as session:
        session.add(MeetingParticipant(
            meeting_id=meeting_id, user_id=user_id, guest_id=guest_id, display_name=display_name,
        ))
        session.commit()


def _names(meeting_id) -> dict:
    with _session_manager.get_session() as session:
        rows = session.exec(select(MeetingParticipant).where(MeetingParticipant.meeting_id == meeting_id)).all()
        return {(row.user_id, row.guest_id): row.display_name for row in rows}


def _rename_traits(guest, name: str) -> dict:
    return {"handle": service.guest_handle(guest.id), "name": name}


@pytest.mark.asyncio
async def test_rename_changes_only_that_guests_participant(kratos):
    meeting_id = _open_meeting()
    renamed = make_guest(kratos, meeting_id, "민수")
    other = make_guest(kratos, meeting_id, "지수")
    _add_participant(meeting_id, "민수", guest_id=renamed.id)
    _add_participant(meeting_id, "지수", guest_id=other.id)
    _add_participant(meeting_id, "민수", user_id="member")

    allowed = await service.settings_change_allowed("profile", renamed.identity_id, "guest", _rename_traits(renamed, "철수"))

    assert allowed is True
    assert _names(meeting_id) == {
        (None, renamed.id): "철수",
        (None, other.id): "지수",
        ("member", None): "민수",
    }


@pytest.mark.asyncio
async def test_rename_without_participant_changes_nothing_else(kratos):
    meeting_id = _open_meeting()
    guest = make_guest(kratos, meeting_id, "민수")
    _add_participant(meeting_id, "회원", user_id="member")

    assert await service.settings_change_allowed("profile", guest.identity_id, "guest", _rename_traits(guest, "철수"))

    assert _names(meeting_id) == {("member", None): "회원"}


@pytest.mark.asyncio
async def test_refused_rename_keeps_participant_name(kratos):
    """다른 게스트가 쓰는 이름으로는 바뀌지 않고 참여자 이름도 그대로다"""
    meeting_id = _open_meeting()
    guest = make_guest(kratos, meeting_id, "민수")
    make_guest(kratos, meeting_id, "지수")
    _add_participant(meeting_id, "민수", guest_id=guest.id)

    assert not await service.settings_change_allowed("profile", guest.identity_id, "guest", _rename_traits(guest, "지수"))

    assert _names(meeting_id) == {(None, guest.id): "민수"}
