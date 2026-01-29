"""
Meeting CRUD 함수

일정 조율 데이터 접근 레이어
"""
from datetime import date, time
from typing import Optional
from uuid import UUID

from sqlmodel import Session, select

from app.domain.meeting.schema.dto import MeetingCreate, MeetingUpdate
from app.models.meeting import Meeting, MeetingParticipant, MeetingTimeSlot


# ============================================================
# Meeting CRUD
# ============================================================

def create_meeting(
        session: Session,
        data: MeetingCreate,
        owner_id: str,
) -> Meeting:
    """일정 조율 생성"""
    meeting_data = data.model_dump(exclude={'visibility'})
    meeting_data['owner_id'] = owner_id
    meeting = Meeting.model_validate(meeting_data)
    session.add(meeting)
    session.flush()
    session.refresh(meeting)
    return meeting


def get_meeting(
        session: Session,
        meeting_id: UUID,
        owner_id: str,
) -> Optional[Meeting]:
    """ID로 일정 조율 조회 (owner_id 검증 포함)"""
    statement = (
        select(Meeting)
        .where(Meeting.id == meeting_id)
        .where(Meeting.owner_id == owner_id)
    )
    return session.exec(statement).first()


def get_meeting_by_id(
        session: Session,
        meeting_id: UUID,
) -> Optional[Meeting]:
    """ID로 일정 조율 조회 (소유자 검증 없음 - 접근 제어는 Service에서 처리)"""
    return session.get(Meeting, meeting_id)


def get_meetings(
        session: Session,
        owner_id: str,
) -> list[Meeting]:
    """소유자의 모든 일정 조율 조회"""
    statement = select(Meeting).where(Meeting.owner_id == owner_id)
    results = session.exec(statement)
    return results.all()


def update_meeting(
        session: Session,
        meeting: Meeting,
        data: MeetingUpdate,
) -> Meeting:
    """일정 조율 업데이트"""
    update_dict = data.model_dump(exclude_unset=True, exclude={'visibility'})
    
    for key, value in update_dict.items():
        setattr(meeting, key, value)
    
    session.flush()
    session.refresh(meeting)
    return meeting


def delete_meeting(session: Session, meeting: Meeting) -> None:
    """일정 조율 삭제"""
    session.delete(meeting)
    session.flush()


# ============================================================
# MeetingParticipant CRUD
# ============================================================

def create_participant(
        session: Session,
        meeting_id: UUID,
        user_id: Optional[str],
        display_name: str,
) -> MeetingParticipant:
    """참여자 생성"""
    participant = MeetingParticipant(
        meeting_id=meeting_id,
        user_id=user_id,
        display_name=display_name,
    )
    session.add(participant)
    session.flush()
    session.refresh(participant)
    return participant


def get_participant(
        session: Session,
        meeting_id: UUID,
        participant_id: UUID,
) -> Optional[MeetingParticipant]:
    """참여자 조회"""
    statement = (
        select(MeetingParticipant)
        .where(MeetingParticipant.id == participant_id)
        .where(MeetingParticipant.meeting_id == meeting_id)
    )
    return session.exec(statement).first()


def get_participants(
        session: Session,
        meeting_id: UUID,
) -> list[MeetingParticipant]:
    """일정 조율의 모든 참여자 조회"""
    statement = (
        select(MeetingParticipant)
        .where(MeetingParticipant.meeting_id == meeting_id)
        .order_by(MeetingParticipant.created_at)
    )
    results = session.exec(statement)
    return results.all()


def get_participant_by_user_id(
        session: Session,
        meeting_id: UUID,
        user_id: str,
) -> Optional[MeetingParticipant]:
    """사용자 ID로 참여자 조회"""
    statement = (
        select(MeetingParticipant)
        .where(MeetingParticipant.meeting_id == meeting_id)
        .where(MeetingParticipant.user_id == user_id)
    )
    return session.exec(statement).first()


# ============================================================
# MeetingTimeSlot CRUD
# ============================================================

def create_time_slot(
        session: Session,
        participant_id: UUID,
        slot_date: date,
        start_time: time,
        end_time: time,
) -> MeetingTimeSlot:
    """시간 슬롯 생성"""
    time_slot = MeetingTimeSlot(
        participant_id=participant_id,
        slot_date=slot_date,
        start_time=start_time,
        end_time=end_time,
    )
    session.add(time_slot)
    session.flush()
    session.refresh(time_slot)
    return time_slot


def get_participant_time_slots(
        session: Session,
        participant_id: UUID,
) -> list[MeetingTimeSlot]:
    """참여자의 모든 시간 슬롯 조회"""
    statement = (
        select(MeetingTimeSlot)
        .where(MeetingTimeSlot.participant_id == participant_id)
        .order_by(MeetingTimeSlot.slot_date, MeetingTimeSlot.start_time)
    )
    results = session.exec(statement)
    return results.all()


def delete_participant_time_slots(
        session: Session,
        participant_id: UUID,
) -> int:
    """참여자의 모든 시간 슬롯 삭제"""
    statement = select(MeetingTimeSlot).where(
        MeetingTimeSlot.participant_id == participant_id
    )
    time_slots = list(session.exec(statement).all())
    count = len(time_slots)
    for slot in time_slots:
        session.delete(slot)
    session.flush()
    return count
