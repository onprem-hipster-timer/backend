"""
Friendship CRUD 함수

친구 관계 데이터 접근 레이어
"""
from typing import Optional
from uuid import UUID

from sqlmodel import Session, select, or_, and_

from app.models.friendship import Friendship, FriendshipStatus


def create_friendship(
    session: Session,
    requester_id: str,
    addressee_id: str,
    status: FriendshipStatus = FriendshipStatus.PENDING,
) -> Friendship:
    """친구 관계 생성"""
    friendship = Friendship(
        requester_id=requester_id,
        addressee_id=addressee_id,
        status=status,
    )
    session.add(friendship)
    session.flush()
    session.refresh(friendship)
    return friendship


def get_friendship(session: Session, friendship_id: UUID) -> Optional[Friendship]:
    """ID로 친구 관계 조회"""
    return session.get(Friendship, friendship_id)


def get_friendship_between(
    session: Session,
    user_id_1: str,
    user_id_2: str,
) -> Optional[Friendship]:
    """두 사용자 간의 친구 관계 조회 (방향 무관)"""
    statement = select(Friendship).where(
        or_(
            and_(
                Friendship.requester_id == user_id_1,
                Friendship.addressee_id == user_id_2,
            ),
            and_(
                Friendship.requester_id == user_id_2,
                Friendship.addressee_id == user_id_1,
            ),
        )
    )
    return session.exec(statement).first()


def get_pending_requests_received(
    session: Session,
    user_id: str,
) -> list[Friendship]:
    """받은 친구 요청 목록 조회 (대기 중)"""
    statement = select(Friendship).where(
        Friendship.addressee_id == user_id,
        Friendship.status == FriendshipStatus.PENDING,
    )
    return list(session.exec(statement).all())


def get_pending_requests_sent(
    session: Session,
    user_id: str,
) -> list[Friendship]:
    """보낸 친구 요청 목록 조회 (대기 중)"""
    statement = select(Friendship).where(
        Friendship.requester_id == user_id,
        Friendship.status == FriendshipStatus.PENDING,
    )
    return list(session.exec(statement).all())


def get_friends(session: Session, user_id: str) -> list[Friendship]:
    """수락된 친구 목록 조회"""
    statement = select(Friendship).where(
        Friendship.status == FriendshipStatus.ACCEPTED,
        or_(
            Friendship.requester_id == user_id,
            Friendship.addressee_id == user_id,
        ),
    )
    return list(session.exec(statement).all())


def get_friend_ids(session: Session, user_id: str) -> list[str]:
    """친구 ID 목록만 조회 (효율적인 쿼리)"""
    friendships = get_friends(session, user_id)
    friend_ids = []
    for f in friendships:
        if f.requester_id == user_id:
            friend_ids.append(f.addressee_id)
        else:
            friend_ids.append(f.requester_id)
    return friend_ids


def get_blocked_users(session: Session, user_id: str) -> list[Friendship]:
    """차단한 사용자 목록 조회"""
    statement = select(Friendship).where(
        Friendship.status == FriendshipStatus.BLOCKED,
        Friendship.blocked_by == user_id,
    )
    return list(session.exec(statement).all())


def is_friend(session: Session, user_id_1: str, user_id_2: str) -> bool:
    """두 사용자가 친구인지 확인"""
    friendship = get_friendship_between(session, user_id_1, user_id_2)
    return friendship is not None and friendship.status == FriendshipStatus.ACCEPTED


def is_blocked(session: Session, blocker_id: str, blocked_id: str) -> bool:
    """차단 여부 확인"""
    friendship = get_friendship_between(session, blocker_id, blocked_id)
    return (
        friendship is not None
        and friendship.status == FriendshipStatus.BLOCKED
        and friendship.blocked_by == blocker_id
    )


def update_friendship_status(
    session: Session,
    friendship: Friendship,
    status: FriendshipStatus,
    blocked_by: Optional[str] = None,
) -> Friendship:
    """친구 관계 상태 업데이트"""
    friendship.status = status
    if status == FriendshipStatus.BLOCKED:
        friendship.blocked_by = blocked_by
    else:
        friendship.blocked_by = None
    session.flush()
    session.refresh(friendship)
    return friendship


def delete_friendship(session: Session, friendship: Friendship) -> None:
    """친구 관계 삭제"""
    session.delete(friendship)
    session.flush()
