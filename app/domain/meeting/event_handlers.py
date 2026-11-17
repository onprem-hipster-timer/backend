"""
게스트 이벤트를 받아 미팅의 게스트 참여자를 맞추는 핸들러

- GuestRenamed: 그 게스트의 참여자 표시 이름(display_name)을 새 이름으로 바꾼다. 회원 참여자는 바꾸지 않는다

게스트가 폐기되면 DB가 그 게스트의 참여자와 가능 시간을 지운다(meeting_participant.guest_id의 ON DELETE CASCADE).

테스트: tests/domain/guest/test_meeting_participation.py
"""
from sqlmodel import Session

from app.crud import meeting as crud
from app.domain.guest.events import GuestRenamed
from app.domain.visibility.enums import ResourceType
from app.shared.messagebus import register


@register(GuestRenamed)
def rename_guest_participant(event: GuestRenamed, session: Session) -> None:
    if event.resource_type != ResourceType.MEETING:
        return
    participant = crud.get_participant_by_guest_id(session, event.guest_id)
    if participant is not None:
        participant.display_name = event.name
