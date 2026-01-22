"""
Friend Service

친구 관계 비즈니스 로직
"""
from uuid import UUID

from sqlmodel import Session

from app.core.auth import CurrentUser
from app.crud import friendship as crud
from app.domain.friend.exceptions import (
    FriendshipNotFoundError,
    FriendRequestAlreadyExistsError,
    AlreadyFriendsError,
    CannotFriendSelfError,
    FriendRequestNotPendingError,
    NotFriendRequestRecipientError,
    UserBlockedError,
    NotFriendsError,
)
from app.domain.friend.model import Friendship, FriendshipStatus
from app.domain.friend.schema.dto import FriendRead, PendingRequestRead


class FriendService:
    """
    Friend Service - 친구 관계 비즈니스 로직

    기존 코드베이스 패턴을 따릅니다:
    - __init__(session, current_user) 패턴
    - CRUD 함수 직접 사용
    - 도메인 예외 발생
    """

    def __init__(self, session: Session, current_user: CurrentUser):
        self.session = session
        self.current_user = current_user
        self.user_id = current_user.sub

    def send_friend_request(self, addressee_id: str) -> Friendship:
        """
        친구 요청 보내기

        비즈니스 로직:
        - 자기 자신에게 요청 불가
        - 이미 친구인 경우 불가
        - 이미 요청이 존재하는 경우 불가
        - 차단 관계인 경우 불가

        :param addressee_id: 친구 요청 대상 사용자 ID
        :return: 생성된 친구 관계
        """
        # 자기 자신에게 요청 불가
        if self.user_id == addressee_id:
            raise CannotFriendSelfError()

        # 기존 관계 확인
        existing = crud.get_friendship_between(self.session, self.user_id, addressee_id)

        if existing:
            if existing.status == FriendshipStatus.ACCEPTED:
                raise AlreadyFriendsError()
            elif existing.status == FriendshipStatus.BLOCKED:
                raise UserBlockedError()
            elif existing.status == FriendshipStatus.PENDING:
                raise FriendRequestAlreadyExistsError()

        # 친구 요청 생성
        friendship = crud.create_friendship(
            self.session,
            requester_id=self.user_id,
            addressee_id=addressee_id,
            status=FriendshipStatus.PENDING,
        )

        return friendship

    def accept_friend_request(self, friendship_id: UUID) -> Friendship:
        """
        친구 요청 수락

        비즈니스 로직:
        - 요청 수신자만 수락 가능
        - PENDING 상태인 요청만 수락 가능

        :param friendship_id: 친구 관계 ID
        :return: 업데이트된 친구 관계
        """
        friendship = crud.get_friendship(self.session, friendship_id)
        if not friendship:
            raise FriendshipNotFoundError()

        # 수신자만 수락 가능
        if friendship.addressee_id != self.user_id:
            raise NotFriendRequestRecipientError()

        # PENDING 상태만 수락 가능
        if friendship.status != FriendshipStatus.PENDING:
            raise FriendRequestNotPendingError()

        # 상태 업데이트
        friendship = crud.update_friendship_status(
            self.session,
            friendship,
            FriendshipStatus.ACCEPTED,
        )

        return friendship

    def reject_friend_request(self, friendship_id: UUID) -> None:
        """
        친구 요청 거절 (삭제)

        비즈니스 로직:
        - 요청 수신자만 거절 가능
        - PENDING 상태인 요청만 거절 가능

        :param friendship_id: 친구 관계 ID
        """
        friendship = crud.get_friendship(self.session, friendship_id)
        if not friendship:
            raise FriendshipNotFoundError()

        # 수신자만 거절 가능
        if friendship.addressee_id != self.user_id:
            raise NotFriendRequestRecipientError()

        # PENDING 상태만 거절 가능
        if friendship.status != FriendshipStatus.PENDING:
            raise FriendRequestNotPendingError()

        # 친구 요청 삭제
        crud.delete_friendship(self.session, friendship)

    def cancel_friend_request(self, friendship_id: UUID) -> None:
        """
        보낸 친구 요청 취소

        비즈니스 로직:
        - 요청 발신자만 취소 가능
        - PENDING 상태인 요청만 취소 가능

        :param friendship_id: 친구 관계 ID
        """
        friendship = crud.get_friendship(self.session, friendship_id)
        if not friendship:
            raise FriendshipNotFoundError()

        # 발신자만 취소 가능
        if friendship.requester_id != self.user_id:
            raise NotFriendRequestRecipientError()

        # PENDING 상태만 취소 가능
        if friendship.status != FriendshipStatus.PENDING:
            raise FriendRequestNotPendingError()

        # 친구 요청 삭제
        crud.delete_friendship(self.session, friendship)

    def remove_friend(self, friendship_id: UUID) -> None:
        """
        친구 삭제 (양방향)

        :param friendship_id: 친구 관계 ID
        """
        friendship = crud.get_friendship(self.session, friendship_id)
        if not friendship:
            raise FriendshipNotFoundError()

        # 양쪽 모두 삭제 가능
        if friendship.requester_id != self.user_id and friendship.addressee_id != self.user_id:
            raise NotFriendsError()

        # 친구 관계 삭제
        crud.delete_friendship(self.session, friendship)

    def block_user(self, target_user_id: str) -> Friendship:
        """
        사용자 차단

        비즈니스 로직:
        - 자기 자신 차단 불가
        - 기존 친구 관계가 있으면 차단으로 변경
        - 없으면 새로운 차단 관계 생성

        :param target_user_id: 차단할 사용자 ID
        :return: 차단 관계
        """
        if self.user_id == target_user_id:
            raise CannotFriendSelfError()

        existing = crud.get_friendship_between(self.session, self.user_id, target_user_id)

        if existing:
            if existing.status == FriendshipStatus.BLOCKED and existing.blocked_by == self.user_id:
                # 이미 차단한 상태
                return existing

            # 상태를 차단으로 변경
            return crud.update_friendship_status(
                self.session,
                existing,
                FriendshipStatus.BLOCKED,
                blocked_by=self.user_id,
            )
        else:
            # 새로운 차단 관계 생성
            friendship = crud.create_friendship(
                self.session,
                requester_id=self.user_id,
                addressee_id=target_user_id,
                status=FriendshipStatus.BLOCKED,
            )
            friendship.blocked_by = self.user_id
            self.session.flush()
            self.session.refresh(friendship)
            return friendship

    def unblock_user(self, target_user_id: str) -> None:
        """
        사용자 차단 해제

        :param target_user_id: 차단 해제할 사용자 ID
        """
        existing = crud.get_friendship_between(self.session, self.user_id, target_user_id)

        if not existing:
            raise FriendshipNotFoundError()

        if existing.status != FriendshipStatus.BLOCKED:
            raise FriendshipNotFoundError()

        if existing.blocked_by != self.user_id:
            # 상대방이 차단한 경우 해제 불가
            raise UserBlockedError()

        # 차단 관계 삭제
        crud.delete_friendship(self.session, existing)

    def get_friends(self) -> list[FriendRead]:
        """
        친구 목록 조회

        :return: 친구 목록
        """
        friendships = crud.get_friends(self.session, self.user_id)

        friends = []
        for f in friendships:
            # 상대방 ID 결정
            friend_id = f.addressee_id if f.requester_id == self.user_id else f.requester_id
            friends.append(FriendRead(
                user_id=friend_id,
                friendship_id=f.id,
                since=f.updated_at,  # 수락 시점
            ))

        return friends

    def get_friend_ids(self) -> list[str]:
        """
        친구 ID 목록만 조회 (효율적인 쿼리)

        :return: 친구 ID 목록
        """
        return crud.get_friend_ids(self.session, self.user_id)

    def get_pending_requests_received(self) -> list[PendingRequestRead]:
        """
        받은 친구 요청 목록 조회

        :return: 대기 중인 친구 요청 목록
        """
        friendships = crud.get_pending_requests_received(self.session, self.user_id)

        return [
            PendingRequestRead(
                id=f.id,
                requester_id=f.requester_id,
                addressee_id=f.addressee_id,
                created_at=f.created_at,
            )
            for f in friendships
        ]

    def get_pending_requests_sent(self) -> list[PendingRequestRead]:
        """
        보낸 친구 요청 목록 조회

        :return: 대기 중인 친구 요청 목록
        """
        friendships = crud.get_pending_requests_sent(self.session, self.user_id)

        return [
            PendingRequestRead(
                id=f.id,
                requester_id=f.requester_id,
                addressee_id=f.addressee_id,
                created_at=f.created_at,
            )
            for f in friendships
        ]

    def is_friend(self, other_user_id: str) -> bool:
        """
        특정 사용자와 친구인지 확인

        :param other_user_id: 확인할 사용자 ID
        :return: 친구 여부
        """
        return crud.is_friend(self.session, self.user_id, other_user_id)

    def is_blocked_by(self, other_user_id: str) -> bool:
        """
        특정 사용자에게 차단당했는지 확인

        :param other_user_id: 확인할 사용자 ID
        :return: 차단 여부
        """
        return crud.is_blocked(self.session, other_user_id, self.user_id)

    def has_blocked(self, other_user_id: str) -> bool:
        """
        특정 사용자를 차단했는지 확인

        :param other_user_id: 확인할 사용자 ID
        :return: 차단 여부
        """
        return crud.is_blocked(self.session, self.user_id, other_user_id)
