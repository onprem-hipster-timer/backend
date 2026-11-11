"""
회원 파기 CRUD

사용자 데이터에는 users 테이블로 가는 FK가 없어 sub로 직접 지운다. 행마다 서비스를 거치지 않고
일괄 DELETE와 DB의 ON DELETE CASCADE(태그 연결, 미팅 참여·가능 시간, 허용 목록)로 지운다.
"""
from datetime import datetime

from sqlalchemy import delete, func, or_, update
from sqlmodel import Session, select

from app.models.account_deletion import AccountDeletion
from app.models.friendship import Friendship
from app.models.meeting import Meeting, MeetingParticipant
from app.models.schedule import Schedule, ScheduleException
from app.models.tag import Tag, TagGroup
from app.models.timer import TimerSession
from app.models.todo import Todo
from app.models.user_profile import UserProfile
from app.models.visibility import ResourceVisibility, VisibilityAllowEmail, VisibilityAllowList


def get_purgeable_profile(session: Session, sub: str, cutoff: datetime) -> UserProfile | None:
    """cutoff 이전에 탈퇴를 신청한 프로필을 잠가서 조회 (취소했거나 이미 지웠으면 None)"""
    statement = (
        select(UserProfile)
        .where(UserProfile.sub == sub, UserProfile.deletion_requested_at <= cutoff)
        .with_for_update()
    )
    return session.exec(statement).first()


def get_purgeable_subs(session: Session, cutoff: datetime) -> list[str]:
    """cutoff 이전에 탈퇴를 신청한 sub"""
    statement = select(UserProfile.sub).where(UserProfile.deletion_requested_at <= cutoff)
    return list(session.exec(statement).all())


def delete_user_data(session: Session, sub: str, verified_email: str | None) -> None:
    """sub의 모든 데이터와 다른 사용자 데이터 속 sub의 흔적을 지운다 (commit 없음)

    순서: todo.tag_group_id가 RESTRICT라 Todo를 태그 그룹보다 먼저 지운다.
    """
    session.execute(delete(TimerSession).where(TimerSession.owner_id == sub))
    session.execute(delete(ScheduleException).where(ScheduleException.owner_id == sub))
    session.execute(delete(Schedule).where(Schedule.owner_id == sub))
    session.execute(delete(Todo).where(Todo.owner_id == sub))
    session.execute(delete(Tag).where(Tag.owner_id == sub))
    session.execute(delete(TagGroup).where(TagGroup.owner_id == sub))
    session.execute(delete(Meeting).where(Meeting.owner_id == sub))
    session.execute(delete(MeetingParticipant).where(MeetingParticipant.user_id == sub))
    session.execute(delete(ResourceVisibility).where(ResourceVisibility.owner_id == sub))
    session.execute(delete(VisibilityAllowList).where(VisibilityAllowList.allowed_user_id == sub))
    if verified_email:
        session.execute(delete(VisibilityAllowEmail).where(func.lower(VisibilityAllowEmail.email) == verified_email))
    session.execute(delete(Friendship).where(or_(Friendship.requester_id == sub, Friendship.addressee_id == sub)))
    session.execute(delete(UserProfile).where(UserProfile.sub == sub))


def add_deleted_account(session: Session, sub: str, purged_at: datetime) -> None:
    session.add(AccountDeletion(sub=sub, purged_at=purged_at))
    session.flush()


def get_kratos_pending_subs(session: Session) -> list[str]:
    """Kratos identity 삭제가 남은 sub"""
    statement = select(AccountDeletion.sub).where(AccountDeletion.kratos_deleted_at.is_(None))
    return list(session.exec(statement).all())


def mark_kratos_deleted(session: Session, sub: str, at: datetime) -> None:
    session.execute(update(AccountDeletion).where(AccountDeletion.sub == sub).values(kratos_deleted_at=at))


def delete_records_deleted_before(session: Session, before: datetime) -> None:
    """Kratos identity를 before 이전에 지운 기록을 지운다"""
    session.execute(delete(AccountDeletion).where(AccountDeletion.kratos_deleted_at <= before))
