"""
Meeting 모델

일정 조율 서비스를 위한 모델들
"""
from datetime import date, time
from enum import Enum
from typing import List, TYPE_CHECKING
from uuid import UUID

from pydantic import NaiveDatetime
from sqlalchemy import Boolean, Column, Enum as SQLEnum, ForeignKey, JSON, CheckConstraint, UniqueConstraint, false
from sqlalchemy.types import TypeDecorator
from sqlmodel import Field, Relationship

from app.models.base import UUIDBase, TimestampMixin

if TYPE_CHECKING:
    pass


class MeetingMode(str, Enum):
    """참여자가 미팅에 답하는 방식. 프론트엔드는 이 값으로 화면을 정한다"""
    HOURLY = "hourly"  # 날짜와 하루 시간 범위 안에서 시간을 고른다
    DAILY = "daily"  # 날짜만 고른다. 하루 전체가 한 답이다
    WEEKLY = "weekly"  # 요일만 고른다 (매주 반복)


class DateList(TypeDecorator):
    """date 목록을 ISO 날짜 문자열의 JSON 배열로 저장한다"""
    impl = JSON
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return [day.isoformat() for day in value]

    def process_result_value(self, value, dialect):
        return [date.fromisoformat(day) for day in value]


class Meeting(UUIDBase, TimestampMixin, table=True):
    """
    일정 조율 (Meeting Poll)
    
    다수의 참여자가 공통으로 가능한 날짜와 시간을 선택하여
    최적의 일정을 도출할 수 있는 일정 조율 서비스
    """
    __tablename__ = "meeting"

    # 소유자 (OIDC sub claim)
    owner_id: str = Field(index=True)

    # 기본 정보
    title: str
    description: str | None = None

    # 일정 기간. 첫날과 마지막 날은 언제나 미팅 날짜다
    start_date: date
    end_date: date

    # 기간에서 빼는 날짜. 기간 안쪽(첫날·마지막 날이 아닌 날)만, 겹치지 않게 정렬해 둔다 (MeetingCreate)
    excluded_dates: List[date] = Field(
        default_factory=list,
        sa_column=Column(DateList, nullable=False),
    )

    # 날짜·시간을 해석하는 IANA 시간대 (예: Asia/Seoul)
    timezone: str

    # 답하는 방식. 바꿔도 저장된 날짜와 가능 시간은 그대로다
    mode: MeetingMode = Field(
        sa_column=Column(
            SQLEnum(MeetingMode, native_enum=False, values_callable=lambda x: [e.value for e in x]),
            nullable=False,
        )
    )

    # 시간 범위 설정
    start_time: time  # 하루 시작 시간
    end_time: time  # 하루 종료 시간 (포함하지 않음, 00:00이면 다음 날 00:00)
    time_slot_minutes: int = Field(default=30)  # 시간 선택 단위 (분)

    # 게스트를 받는지. 공개 범위가 PUBLIC일 때만 켤 수 있다 (MeetingService)
    allow_guests: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=false()),
    )

    __table_args__ = (
        CheckConstraint("start_date <= end_date", name="ck_meeting_date_range"),
        # end_time 00:00은 하루의 끝. SQLite는 time을 'HH:MM:SS.ffffff' 문자열로 저장한다
        CheckConstraint(
            "start_time < end_time OR end_time IN ('00:00:00', '00:00:00.000000')",
            name="ck_meeting_time_range",
        ),
        CheckConstraint("time_slot_minutes > 0", name="ck_meeting_time_slot"),
    )

    # Relationships
    # 참여자·가능 시간은 DB의 ON DELETE CASCADE가 지운다 (ORM이 FK를 NULL로 바꾸지 않게)
    participants: List["MeetingParticipant"] = Relationship(
        back_populates="meeting",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "passive_deletes": True},
    )


class MeetingParticipant(UUIDBase, TimestampMixin, table=True):
    """
    일정 조율 참여자
    
    참여자 정보와 선택한 가능 시간을 저장
    """
    __tablename__ = "meeting_participant"

    # 일정 조율 참조
    meeting_id: UUID = Field(
        sa_column=Column(
            ForeignKey("meeting.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )

    # 참여자 정보
    user_id: str | None = Field(default=None, index=True)  # OIDC sub (로그인한 경우)
    # 게스트 참여자의 게스트 행. 게스트 행이 지워지면 DB가 참여자와 가능 시간을 지운다
    guest_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            ForeignKey("guest.id", ondelete="CASCADE", name="fk_meeting_participant_guest_id"),
            nullable=True,
        ),
    )
    display_name: str  # 표시 이름 (닉네임). 게스트 참여자는 게스트 이름

    __table_args__ = (
        # 미팅마다 사용자당 참여자 한 명 (user_id가 NULL인 행은 제한하지 않음)
        UniqueConstraint("meeting_id", "user_id", name="uq_meeting_participant_meeting_user"),
        # 게스트마다 참여자 한 명
        UniqueConstraint("guest_id", name="uq_meeting_participant_guest"),
        # 회원 참여자이면서 게스트 참여자일 수 없다 (둘 다 NULL인 예전 행은 둔다)
        CheckConstraint("user_id IS NULL OR guest_id IS NULL", name="ck_meeting_participant_user_or_guest"),
    )

    # Relationships
    meeting: "Meeting" = Relationship(back_populates="participants")
    time_slots: List["MeetingTimeSlot"] = Relationship(
        back_populates="participant",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "passive_deletes": True},
    )


class MeetingTimeSlot(UUIDBase, table=True):
    """
    참여자가 선택한 가능 시간 슬롯

    반열린 구간 [start_time, end_time)을 받은 그대로 저장한다. 미팅의 날짜·시간·칸과는 무관하다
    """
    __tablename__ = "meeting_time_slot"

    # 참여자 참조
    participant_id: UUID = Field(
        sa_column=Column(
            ForeignKey("meeting_participant.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )

    # 가능 시간 (UTC naive, end_time은 포함하지 않음)
    start_time: NaiveDatetime
    end_time: NaiveDatetime

    __table_args__ = (
        CheckConstraint("start_time < end_time", name="ck_time_slot_range"),
    )

    # Relationships
    participant: "MeetingParticipant" = Relationship(back_populates="time_slots")
