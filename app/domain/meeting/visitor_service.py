"""
로그인하지 않은 방문자와 게스트의 미팅 사용 (회원은 MeetingService, MeetingResultService)

- 보이는 미팅: 공개 범위가 PUBLIC이고 소유자가 휴면 계정이 아닌 미팅(is_public). 아니면 없는 미팅과 같은 MeetingNotFoundError
- 응답에 회원의 sub(미팅의 owner_id, 참여자의 user_id)를 넣지 않는다
- 방문자(MeetingVisitorService): 미팅 정보와 결과 그리드
- 게스트(MeetingGuestService): 방문자가 보는 것에 더해 참여자별 가능 시간, 참여 등록, 자기 가능 시간 설정.
  이 미팅의 게스트이고 호스트 상태가 OPEN인지는 require_guest_access가 확인했다.
  게스트의 참여자는 guest_id로 찾고, 표시 이름은 게스트 이름이다(이름을 바꾸면 event_handlers가 바꾼다)

테스트: tests/domain/guest/test_meeting_access.py, tests/domain/guest/test_meeting_participation.py
"""
from typing import List
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.crud import meeting as crud
from app.domain.guest.model import Guest
from app.domain.meeting.exceptions import MeetingNotFoundError, MeetingParticipantNotFoundError
from app.domain.meeting.result_service import MeetingResultService
from app.domain.meeting.schema.dto import (
    AvailabilityRead,
    MeetingRead,
    MeetingResultRead,
    ParticipantCreate,
    TimeSlotCreate,
)
from app.domain.meeting.service import check_time_slots, replace_time_slots
from app.domain.visibility.enums import ResourceType, VisibilityLevel
from app.domain.visibility.service import is_public
from app.models.meeting import Meeting, MeetingParticipant, MeetingTimeSlot


class MeetingVisitorService:
    """로그인하지 않은 방문자가 보는 미팅 정보와 결과"""

    def __init__(self, session: Session):
        self.session = session

    def get_meeting(self, meeting_id: UUID) -> Meeting:
        """PUBLIC이고 소유자가 휴면 계정이 아닌 미팅. 아니면 MeetingNotFoundError"""
        meeting = crud.get_meeting_by_id(self.session, meeting_id)
        if meeting is None or not is_public(self.session, ResourceType.MEETING, meeting.id, meeting.owner_id):
            raise MeetingNotFoundError()
        return meeting

    def to_read_dto(self, meeting: Meeting) -> MeetingRead:
        """owner_id를 비운 MeetingRead (다른 사람의 PUBLIC 미팅)"""
        meeting_read = MeetingRead.model_validate(meeting)
        meeting_read.owner_id = None
        meeting_read.is_shared = True
        meeting_read.visibility_level = VisibilityLevel.PUBLIC
        return meeting_read

    def get_meeting_result(self, meeting_id: UUID) -> MeetingResultRead:
        meeting = self.get_meeting(meeting_id)
        meeting_read = MeetingRead.model_validate(meeting)
        meeting_read.owner_id = None
        return MeetingResultService(self.session).result_of(meeting, meeting_read)


class MeetingGuestService(MeetingVisitorService):
    """게스트의 참여자별 가능 시간 조회, 참여 등록, 자기 가능 시간 설정"""

    def __init__(self, session: Session, guest: Guest):
        super().__init__(session)
        self.guest = guest

    def get_availability(self, meeting_id: UUID) -> List[AvailabilityRead]:
        """참여자별 가능 시간 (참여자의 user_id는 비운다)"""
        meeting = self.get_meeting(meeting_id)
        return MeetingResultService(self.session).availability_of(meeting, hide_user_ids=True)

    def create_participant(self, meeting_id: UUID) -> tuple[MeetingParticipant, bool]:
        """게스트의 참여자를 만들고 (참여자, 새로 만들었는지)를 돌려준다. 이미 있으면 그 참여자.

        표시 이름은 게스트 이름이다. 같은 게스트의 요청 둘이 동시에 만들려 하면 UNIQUE(guest_id)가 하나만 남긴다.
        """
        self.get_meeting(meeting_id)
        existing = crud.get_participant_by_guest_id(self.session, self.guest.id)
        if existing is not None:
            return existing, False

        # 앞서 쌓인 변경은 SAVEPOINT 밖에서 먼저 flush해, 그 변경의 IntegrityError를 여기서 삼키지 않는다
        self.session.flush()
        try:
            with self.session.begin_nested():
                participant = crud.create_participant(
                    self.session,
                    meeting_id,
                    user_id=None,
                    data=ParticipantCreate(display_name=self.guest.name),
                    guest_id=self.guest.id,
                )
        except IntegrityError:
            existing = crud.get_participant_by_guest_id(self.session, self.guest.id)
            if existing is None:
                raise
            return existing, False
        return participant, True

    def set_time_slots(
            self,
            meeting_id: UUID,
            participant_id: UUID,
            time_slots: List[TimeSlotCreate],
    ) -> List[MeetingTimeSlot]:
        """게스트 자기 참여자의 가능 시간을 바꾼다. 다른 참여자면 없는 참여자와 같은 MeetingParticipantNotFoundError"""
        meeting = self.get_meeting(meeting_id)
        check_time_slots(meeting, time_slots)
        participant = crud.get_participant(self.session, meeting_id, participant_id)
        if participant is None or participant.guest_id != self.guest.id:
            raise MeetingParticipantNotFoundError()
        return replace_time_slots(self.session, participant_id, time_slots)
