"""
Meeting 모델

일정 조율 서비스를 위한 모델들
"""
from datetime import date, time
from typing import List, TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Column, ForeignKey, JSON, CheckConstraint
from sqlmodel import Field, Relationship

from app.models.base import UUIDBase, TimestampMixin

if TYPE_CHECKING:
    pass


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

    # 일정 기간
    start_date: date
    end_date: date

    # 요일 기반 설정 (JSON array of integers 0-6, 0=월요일)
    # 예: [0, 2, 4] = 월, 수, 금
    available_days: List[int] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False)
    )

    # 시간 범위 설정
    start_time: time  # 하루 시작 시간
    end_time: time  # 하루 종료 시간
    time_slot_minutes: int = Field(default=30)  # 시간 선택 단위 (분)

    __table_args__ = (
        CheckConstraint("start_date <= end_date", name="ck_meeting_date_range"),
        CheckConstraint("start_time < end_time", name="ck_meeting_time_range"),
        CheckConstraint("time_slot_minutes > 0", name="ck_meeting_time_slot"),
    )

    # Relationships
    participants: List["MeetingParticipant"] = Relationship(back_populates="meeting")


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
    display_name: str  # 표시 이름 (닉네임)

    # Relationships
    meeting: "Meeting" = Relationship(back_populates="participants")
    time_slots: List["MeetingTimeSlot"] = Relationship(back_populates="participant")


class MeetingTimeSlot(UUIDBase, table=True):
    """
    참여자가 선택한 가능 시간 슬롯
    
    각 참여자가 특정 날짜와 시간 구간을 선택한 것을 저장
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

    # 시간 슬롯 정보
    slot_date: date = Field(index=True)  # 날짜
    start_time: time  # 시작 시간
    end_time: time  # 종료 시간

    __table_args__ = (
        CheckConstraint("start_time < end_time", name="ck_time_slot_range"),
    )

    # Relationships
    participant: "MeetingParticipant" = Relationship(back_populates="time_slots")
