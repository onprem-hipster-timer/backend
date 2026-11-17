"""
Meeting Service

일정 조율 서비스 비즈니스 로직 (CRUD + 참여자 관리)
"""
from bisect import bisect_left
from datetime import date, datetime
from math import ceil
from typing import List
from uuid import UUID

from pydantic import ValidationError
from pydantic.experimental.missing_sentinel import MISSING
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.core.auth import CurrentUser
from app.crud import meeting as crud
from app.crud import visibility as visibility_crud
from app.domain.guest.model import Guest
from app.domain.meeting.exceptions import (
    InvalidMeetingError,
    MeetingNotFoundError,
    MeetingParticipantNotFoundError,
    TooManyTimeSlotsError,
)
from app.domain.meeting.schema.dto import (
    daily_range,
    meeting_dates,
    meeting_day_ranges,
    merge_intervals,
    subtract_intervals,
    MODE_RULE_FIELDS,
    AvailabilityRead,
    MeetingCreate,
    MeetingUpdate,
    MeetingRead,
    ParticipantCreate,
    ParticipantRead,
    TimeSlotCreate,
    TimeSlotRead,
)
from app.domain.visibility.enums import ResourceType
from app.domain.visibility.service import VisibilityService, is_public
from app.models.meeting import Meeting, MeetingMode, MeetingParticipant, MeetingTimeSlot, TimeSlotKind

ALLOW_GUESTS_REQUIRES_PUBLIC = "allow_guests can be true only while the meeting's visibility is public"


class MeetingService:
    """
    Meeting Service - CRUD + 참여자 관리

    일정 조율의 생성/조회/수정/삭제 및 참여자 관리를 담당합니다.
    분석 로직은 MeetingResultService에서 처리합니다.
    """

    def __init__(self, session: Session, current_user: CurrentUser):
        self.session = session
        self.current_user = current_user
        self.owner_id = current_user.sub

    def create_meeting(self, data: MeetingCreate) -> Meeting:
        """
        일정 조율 생성
        
        :param data: 일정 조율 생성 데이터
        :return: 생성된 일정 조율
        :raises InvalidMeetingError: allow_guests가 true인 경우 (새 미팅은 공개 범위 설정이 없어 PRIVATE이다)
        """
        if data.allow_guests:
            raise InvalidMeetingError(ALLOW_GUESTS_REQUIRES_PUBLIC)
        meeting = crud.create_meeting(self.session, data, self.owner_id)
        return meeting

    def get_meeting(self, meeting_id: UUID) -> Meeting:
        """
        일정 조율 조회 (본인 소유만)
        
        :param meeting_id: 일정 조율 ID
        :return: 일정 조율
        :raises MeetingNotFoundError: 일정 조율을 찾을 수 없는 경우
        """
        meeting = crud.get_meeting(self.session, meeting_id, self.owner_id)
        if not meeting:
            raise MeetingNotFoundError()
        return meeting

    def get_meeting_with_access_check(self, meeting_id: UUID) -> tuple[Meeting, bool]:
        """
        일정 조율 조회 (공유 리소스 접근 제어 포함)
        
        본인 소유이거나 공유 접근 권한이 있는 경우 반환합니다.
        
        :param meeting_id: 일정 조율 ID
        :return: (일정 조율, is_shared) 튜플
        :raises MeetingNotFoundError: 일정 조율이 없거나 접근할 수 없는 경우
        """
        # 먼저 ID로만 조회 (소유자 무관)
        meeting = crud.get_meeting_by_id(self.session, meeting_id)
        if not meeting:
            raise MeetingNotFoundError()

        # 본인 소유인 경우
        if meeting.owner_id == self.owner_id:
            return meeting, False

        # 타인 소유인 경우 접근 권한 확인
        visibility_service = VisibilityService(self.session, self.current_user)
        if not visibility_service.can_access(
            resource_type=ResourceType.MEETING,
            resource_id=meeting_id,
            owner_id=meeting.owner_id,
        ):
            raise MeetingNotFoundError()

        return meeting, True

    def get_all_meetings(self) -> List[Meeting]:
        """
        모든 일정 조율 조회 (본인 소유만)
        
        :return: 일정 조율 리스트
        """
        return crud.get_meetings(self.session, self.owner_id)

    def update_meeting(self, meeting_id: UUID, data: MeetingUpdate) -> Meeting:
        """
        일정 조율 업데이트
        
        :param meeting_id: 일정 조율 ID
        :param data: 업데이트 데이터
        :return: 업데이트된 일정 조율
        :raises MeetingNotFoundError: 일정 조율을 찾을 수 없는 경우
        :raises InvalidMeetingError: 저장된 값에 수정 내용을 합친 미팅이 생성 규칙을 어기는 경우
            (방식의 규칙은 MODE_RULE_FIELDS가 바뀔 때만), allow_guests에 true를 보냈는데 공개 범위가 PUBLIC이 아닌 경우
        """
        meeting = crud.get_meeting(self.session, meeting_id, self.owner_id)
        if not meeting:
            raise MeetingNotFoundError()

        if data.allow_guests is True and not is_public(
                self.session, ResourceType.MEETING, meeting_id, meeting.owner_id,
        ):
            raise InvalidMeetingError(ALLOW_GUESTS_REQUIRES_PUBLIC)
        self._validate_merged(meeting, data)
        updated_meeting = crud.update_meeting(self.session, meeting, data)
        return updated_meeting

    @staticmethod
    def _validate_merged(meeting: Meeting, data: MeetingUpdate) -> None:
        """저장된 값에 수정 내용을 합친 결과를 MeetingCreate 규칙으로 검증한다.

        apply_update와 같이 보내지 않은 필드와 NOT NULL 필드의 null은 저장된 값을 쓴다.
        방식의 규칙은 MODE_RULE_FIELDS 중 하나라도 저장된 값과 달라질 때만 본다.
        그래서 규칙을 어기는 저장된 미팅도 제목처럼 규칙과 무관한 필드는 고칠 수 있다.
        """
        merged = {name: getattr(meeting, name) for name in MeetingCreate.model_fields}
        columns = Meeting.__table__.columns
        for key, value in data.model_dump().items():
            if value is MISSING or (value is None and not columns[key].nullable):
                continue
            merged[key] = value
        rules_changed = any(merged[name] != getattr(meeting, name) for name in MODE_RULE_FIELDS)
        try:
            MeetingCreate.model_validate(merged, context={"skip_mode_rules": not rules_changed})
        except ValidationError as e:
            raise InvalidMeetingError(
                "; ".join(error["msg"] for error in e.errors(include_url=False))
            ) from None

    def delete_meeting(self, meeting_id: UUID) -> None:
        """
        일정 조율 삭제
        
        :param meeting_id: 일정 조율 ID
        :raises MeetingNotFoundError: 일정 조율을 찾을 수 없는 경우
        """
        meeting = crud.get_meeting(self.session, meeting_id, self.owner_id)
        if not meeting:
            raise MeetingNotFoundError()

        # 접근권한 설정 삭제
        visibility_crud.delete_visibility_by_resource(
            self.session, ResourceType.MEETING, meeting_id
        )

        crud.delete_meeting(self.session, meeting)

    def create_participant(
            self,
            meeting_id: UUID,
            data: ParticipantCreate,
    ) -> tuple[MeetingParticipant, bool]:
        """
        참여자 등록

        미팅마다 사용자당 참여자는 한 명이다. 이미 참여했으면 그 참여자의 표시 이름을 바꿔 돌려준다.

        :param meeting_id: 일정 조율 ID
        :param data: 참여자 생성 데이터
        :return: (참여자, 새로 만들었는지)
        :raises MeetingNotFoundError: 일정 조율이 없거나 접근할 수 없는 경우
        """
        # 접근 권한 확인
        self.get_meeting_with_access_check(meeting_id)

        participant, created = self._get_or_create_participant(meeting_id, data)
        if not created:
            participant = self._rename_participant(participant, data)
        return participant, created

    def _get_or_create_participant(
            self,
            meeting_id: UUID,
            data: ParticipantCreate,
    ) -> tuple[MeetingParticipant, bool]:
        """이 사용자의 참여자. 없으면 data로 만든다. (참여자, 새로 만들었는지)

        같은 사용자의 요청 둘이 동시에 만들려 하면 unique 제약(uq_meeting_participant_meeting_user)이
        하나만 남긴다. 진 쪽은 SAVEPOINT만 되돌리고 이긴 쪽의 참여자를 다시 읽는다.
        """
        existing = crud.get_participant_by_user_id(self.session, meeting_id, self.owner_id)
        if existing:
            return existing, False

        # 앞서 쌓인 변경은 SAVEPOINT 밖에서 먼저 flush해, 그 변경의 IntegrityError를 여기서 삼키지 않는다
        self.session.flush()
        try:
            with self.session.begin_nested():
                participant = crud.create_participant(
                    self.session, meeting_id, user_id=self.owner_id, data=data,
                )
        except IntegrityError:
            existing = crud.get_participant_by_user_id(self.session, meeting_id, self.owner_id)
            if existing is None:
                raise
            return existing, False

        return participant, True

    def merge_guest(self, meeting_id: UUID, guest: Guest, profile_name: str | None) -> AvailabilityRead:
        """
        게스트 가져오기: 게스트 참여자의 가능 시간을 이 회원의 참여자에 합친다 (merge_time_slots)

        게스트 서비스의 import_guest가 게스트 행을 잠근 트랜잭션 안에서 부르고, 이어서 게스트를 지운다.
        회원 참여자가 없으면 프로필 표시 이름으로 만든다. 표시 이름이 없거나 참여자 이름 규칙에 맞지 않으면 게스트 이름이다.
        있으면 표시 이름은 그대로다. 회원·게스트 참여자와 그 가능 시간은 잠그고 읽는다(NOWAIT).

        :return: 회원 참여자와 합친 가능 시간
        :raises MeetingNotFoundError: 일정 조율이 없거나 접근할 수 없는 경우
        """
        meeting, _ = self.get_meeting_with_access_check(meeting_id)
        try:
            data = ParticipantCreate(display_name=profile_name)
        except ValidationError:
            data = ParticipantCreate(display_name=guest.name)
        participant = crud.get_participant_by_user_id(self.session, meeting_id, self.owner_id, lock=True)
        if participant is None:
            # 같은 회원의 참여자를 다른 요청이 먼저 만들면 unique 제약이 막고(IntegrityError) 트랜잭션 전체가 되돌아간다
            participant = crud.create_participant(self.session, meeting_id, user_id=self.owner_id, data=data)
            member_slots = []
        else:
            member_slots = crud.get_participant_time_slots(self.session, participant.id, lock=True)
        guest_participant = crud.get_participant_by_guest_id(self.session, guest.id, lock=True)
        guest_slots = (
            crud.get_participant_time_slots(self.session, guest_participant.id, lock=True)
            if guest_participant is not None else []
        )
        slots = replace_time_slots(
            self.session, participant.id, merge_time_slots(meeting, member_slots, guest_slots),
        )
        return AvailabilityRead(
            participant=ParticipantRead.from_participant(participant, meeting.owner_id),
            time_slots=[TimeSlotRead.model_validate(slot) for slot in slots],
        )

    def _rename_participant(
            self,
            participant: MeetingParticipant,
            data: ParticipantCreate,
    ) -> MeetingParticipant:
        participant.display_name = data.display_name
        self.session.flush()
        return participant

    def remove_participant(self, meeting_id: UUID, participant_id: UUID) -> str | None:
        """
        참여자 빼기 (소유자만)

        회원 참여자는 지운다. 게스트 참여자는 지우지 않고 그 게스트의 identity id를 돌려준다.
        부르는 쪽이 게스트 서비스의 discard_guest로 게스트를 폐기하면 DB가 참여자를 지운다.
        어느 쪽이든 가능 시간은 DB의 ON DELETE CASCADE가 지운다.

        :param meeting_id: 일정 조율 ID
        :param participant_id: 참여자 ID
        :return: 게스트 참여자면 그 게스트의 Kratos identity id, 아니면 None
        :raises MeetingNotFoundError: 일정 조율이 없거나 소유자가 아닌 경우
        :raises MeetingParticipantNotFoundError: 그 미팅의 참여자가 아닌 경우
        """
        self.get_meeting(meeting_id)

        participant = crud.get_participant(self.session, meeting_id, participant_id)
        if participant is None:
            raise MeetingParticipantNotFoundError()

        if participant.guest_id is None:
            crud.delete_participant(self.session, participant)
            return None

        guest = self.session.get(Guest, participant.guest_id)
        if guest is None:  # 다른 요청이 그 게스트를 막 폐기했다 (참여자도 함께 지워졌다)
            raise MeetingParticipantNotFoundError()
        return guest.identity_id

    def get_participant(
            self,
            meeting_id: UUID,
            participant_id: UUID,
    ) -> MeetingParticipant:
        """
        참여자 조회
        
        :param meeting_id: 일정 조율 ID
        :param participant_id: 참여자 ID
        :return: 참여자
        :raises MeetingNotFoundError: 일정 조율이 없거나 접근할 수 없는 경우
        :raises MeetingParticipantNotFoundError: 참여자를 찾을 수 없는 경우
        """
        # 접근 권한 확인
        self.get_meeting_with_access_check(meeting_id)

        participant = crud.get_participant(
            self.session,
            meeting_id,
            participant_id,
        )
        if not participant:
            raise MeetingParticipantNotFoundError()

        return participant

    def get_participants(self, meeting_id: UUID) -> List[MeetingParticipant]:
        """
        참여자 목록 조회
        
        :param meeting_id: 일정 조율 ID
        :return: 참여자 리스트
        :raises MeetingNotFoundError: 일정 조율이 없거나 접근할 수 없는 경우
        """
        # 접근 권한 확인
        self.get_meeting_with_access_check(meeting_id)

        return crud.get_participants(self.session, meeting_id)

    def set_time_slots(
            self,
            meeting_id: UUID,
            participant_id: UUID,
            time_slots: List[TimeSlotCreate],
    ) -> List[MeetingTimeSlot]:
        """
        참여자의 가능 시간 설정
        
        기존 시간 슬롯을 모두 삭제하고 새로운 시간 슬롯을 설정합니다.
        저장하기 전에 미팅과 함께 보는 규칙은 check_time_slots입니다. 슬롯은 보낸 구간 그대로 저장하고
        칸에 맞추거나 나누지 않습니다.
        
        :param meeting_id: 일정 조율 ID
        :param participant_id: 참여자 ID
        :param time_slots: 시간 슬롯 리스트
        :return: 생성된 시간 슬롯 리스트
        :raises MeetingNotFoundError: 일정 조율이 없거나 접근할 수 없는 경우
        :raises MeetingParticipantNotFoundError: 참여자가 없거나 본인 참여자가 아닌 경우
        :raises TooManyTimeSlotsError: 슬롯 수가 미팅의 칸 수보다 많은 경우
        """
        # 접근 권한 확인
        meeting, _ = self.get_meeting_with_access_check(meeting_id)

        check_time_slots(meeting, time_slots)

        # 참여자 확인
        participant = self.get_participant(meeting_id, participant_id)

        # 참여자가 본인인지 확인 (본인만 수정 가능)
        if participant.user_id != self.owner_id:
            raise MeetingParticipantNotFoundError()

        return replace_time_slots(self.session, participant_id, time_slots)

    @staticmethod
    def _cell_count(meeting: Meeting) -> int:
        """미팅 날짜 수 x 하루 범위(분) / 시간 단위(분), 올림"""
        days = len(meeting_dates(meeting.start_date, meeting.end_date, meeting.excluded_dates))
        daily_minutes = daily_range(meeting.start_time, meeting.end_time).total_seconds() // 60
        return ceil(days * max(daily_minutes, 0) / meeting.time_slot_minutes)

    def to_read_dto(
            self,
            meeting: Meeting,
            is_shared: bool = False,
    ) -> MeetingRead:
        """
        Meeting을 MeetingRead DTO로 변환하고 접근권한 정보를 채웁니다.
        
        :param meeting: Meeting 모델
        :param is_shared: 공유된 리소스인지 여부
        :return: MeetingRead DTO (접근권한 정보 포함)
        """
        meeting_read = MeetingRead.model_validate(meeting)
        meeting_read.owner_id = meeting.owner_id
        meeting_read.is_shared = is_shared

        # 접근권한 레벨 조회
        visibility = visibility_crud.get_visibility_by_resource(
            self.session, ResourceType.MEETING, meeting.id
        )
        if visibility:
            meeting_read.visibility_level = visibility.level

        return meeting_read


def check_time_slots(meeting: Meeting, time_slots: List[TimeSlotCreate]) -> None:
    """가능 시간을 저장하기 전에 미팅과 함께 보는 규칙. 회원과 게스트의 저장이 모두 거친다

    슬롯 수가 미팅의 칸 수(MeetingService._cell_count)보다 많으면 TooManyTimeSlotsError
    """
    limit = MeetingService._cell_count(meeting)
    if len(time_slots) > limit:
        raise TooManyTimeSlotsError(f"Too many time slots: at most {limit} for this meeting")


def merge_time_slots(meeting: Meeting, member_slots: List, guest_slots: List) -> List[TimeSlotCreate]:
    """게스트 가져오기에서 회원의 가능 시간에 게스트의 가능 시간을 합친다 (시작 순)

    - 같은 종류의 구간은 합집합이다. 겹치거나 맞닿은 구간은 하나가 된다
    - 게스트 구간이 회원의 다른 종류 구간과 겹치면 회원의 답을 두고 게스트 구간에서 그 부분을 뺀다
    - 합친 unavailable 구간이 하루 범위에 걸친 날(_days_to_cover)의 빈 시간을 unavailable로 채운다
    - 슬롯 수 제한은 보지 않는다
    """
    def intervals(slots, kind):
        return [(slot.start_time, slot.end_time) for slot in slots if slot.kind == kind]

    member_available = intervals(member_slots, TimeSlotKind.AVAILABLE)
    member_unavailable = intervals(member_slots, TimeSlotKind.UNAVAILABLE)
    available = merge_intervals(
        member_available + subtract_intervals(intervals(guest_slots, TimeSlotKind.AVAILABLE), member_unavailable)
    )
    unavailable = merge_intervals(
        member_unavailable + subtract_intervals(intervals(guest_slots, TimeSlotKind.UNAVAILABLE), member_available)
    )
    covered = merge_intervals(available + unavailable)
    gaps = [
        gap
        for _, start, end in _days_to_cover(meeting, unavailable)
        for gap in subtract_intervals([(start, end)], covered)
    ]
    unavailable = merge_intervals(unavailable + gaps)
    slots = [
        TimeSlotCreate(start_time=start, end_time=end, kind=kind)
        for kind, merged in ((TimeSlotKind.AVAILABLE, available), (TimeSlotKind.UNAVAILABLE, unavailable))
        for start, end in merged
    ]
    return sorted(slots, key=lambda slot: slot.start_time)


def _days_to_cover(
        meeting: Meeting,
        unavailable: List[tuple[datetime, datetime]],
) -> List[tuple[date, datetime, datetime]]:
    """합친 unavailable 구간이 하루 범위에 걸친 묶음의 (날짜, 하루 범위의 시작, 끝). 날짜 순.
    묶음은 hourly면 날마다, daily·weekly면 미팅 날짜 전체다"""
    if not unavailable:
        return []
    ranges = meeting_day_ranges(meeting)
    groups = [[day_range] for day_range in ranges] if meeting.mode == MeetingMode.HOURLY else [ranges]
    return [
        day_range
        for group in groups
        if any(_overlaps(unavailable, start, end) for _, start, end in group)
        for day_range in group
    ]


def _overlaps(merged: List[tuple[datetime, datetime]], start: datetime, end: datetime) -> bool:
    """합친 구간 중 [start, end)와 겹치는 것이 있으면 True (맞닿는 것은 겹치지 않는다)"""
    i = bisect_left(merged, (end,)) - 1  # end 전에 시작하는 마지막 구간
    return i >= 0 and merged[i][1] > start


def replace_time_slots(
        session: Session,
        participant_id: UUID,
        time_slots: List[TimeSlotCreate],
) -> List[MeetingTimeSlot]:
    """참여자의 시간 슬롯을 모두 지우고 time_slots로 바꾼다"""
    crud.delete_participant_time_slots(session, participant_id)
    return [crud.create_time_slot(session, participant_id, slot_data) for slot_data in time_slots]
