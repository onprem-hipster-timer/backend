"""
FriendService 테스트

친구 관계 비즈니스 로직 테스트
"""
import pytest
from uuid import UUID

from app.core.auth import CurrentUser
from app.domain.friend.service import FriendService
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
from app.models.friendship import FriendshipStatus


@pytest.fixture
def second_user() -> CurrentUser:
    """두 번째 테스트 사용자"""
    return CurrentUser(
        sub="second-user-id",
        email="second@example.com",
        name="Second User",
    )


@pytest.fixture
def third_user() -> CurrentUser:
    """세 번째 테스트 사용자"""
    return CurrentUser(
        sub="third-user-id",
        email="third@example.com",
        name="Third User",
    )


class TestFriendRequest:
    """친구 요청 관련 테스트"""

    def test_send_friend_request_success(self, test_session, test_user, second_user):
        """친구 요청 성공"""
        service = FriendService(test_session, test_user)
        
        friendship = service.send_friend_request(second_user.sub)
        
        assert friendship is not None
        assert isinstance(friendship.id, UUID)
        assert friendship.requester_id == test_user.sub
        assert friendship.addressee_id == second_user.sub
        assert friendship.status == FriendshipStatus.PENDING

    def test_send_friend_request_to_self_fails(self, test_session, test_user):
        """자기 자신에게 친구 요청 실패"""
        service = FriendService(test_session, test_user)
        
        with pytest.raises(CannotFriendSelfError):
            service.send_friend_request(test_user.sub)

    def test_send_duplicate_friend_request_fails(self, test_session, test_user, second_user):
        """중복 친구 요청 실패"""
        service = FriendService(test_session, test_user)
        
        # 첫 번째 요청 성공
        service.send_friend_request(second_user.sub)
        
        # 두 번째 요청 실패
        with pytest.raises(FriendRequestAlreadyExistsError):
            service.send_friend_request(second_user.sub)

    def test_send_friend_request_to_already_friend_fails(
        self, test_session, test_user, second_user
    ):
        """이미 친구인 사용자에게 요청 실패"""
        # 친구 관계 생성
        user1_service = FriendService(test_session, test_user)
        friendship = user1_service.send_friend_request(second_user.sub)
        
        user2_service = FriendService(test_session, second_user)
        user2_service.accept_friend_request(friendship.id)
        
        # 이미 친구인 상태에서 요청 시도
        with pytest.raises(AlreadyFriendsError):
            user1_service.send_friend_request(second_user.sub)


class TestAcceptRejectRequest:
    """친구 요청 수락/거절 테스트"""

    def test_accept_friend_request_success(self, test_session, test_user, second_user):
        """친구 요청 수락 성공"""
        # 요청 보내기
        user1_service = FriendService(test_session, test_user)
        friendship = user1_service.send_friend_request(second_user.sub)
        
        # 요청 수락
        user2_service = FriendService(test_session, second_user)
        accepted = user2_service.accept_friend_request(friendship.id)
        
        assert accepted.status == FriendshipStatus.ACCEPTED

    def test_accept_by_non_recipient_fails(self, test_session, test_user, second_user):
        """요청 수신자가 아닌 사람이 수락 시도 실패"""
        user1_service = FriendService(test_session, test_user)
        friendship = user1_service.send_friend_request(second_user.sub)
        
        # 요청을 보낸 사람이 수락 시도
        with pytest.raises(NotFriendRequestRecipientError):
            user1_service.accept_friend_request(friendship.id)

    def test_reject_friend_request_success(self, test_session, test_user, second_user):
        """친구 요청 거절 성공"""
        user1_service = FriendService(test_session, test_user)
        friendship = user1_service.send_friend_request(second_user.sub)
        
        user2_service = FriendService(test_session, second_user)
        user2_service.reject_friend_request(friendship.id)
        
        # 거절된 요청은 삭제됨
        with pytest.raises(FriendshipNotFoundError):
            user2_service.accept_friend_request(friendship.id)

    def test_cancel_friend_request_success(self, test_session, test_user, second_user):
        """보낸 친구 요청 취소 성공"""
        service = FriendService(test_session, test_user)
        friendship = service.send_friend_request(second_user.sub)
        
        service.cancel_friend_request(friendship.id)
        
        # 취소된 요청은 삭제됨
        with pytest.raises(FriendshipNotFoundError):
            service.cancel_friend_request(friendship.id)


class TestFriendList:
    """친구 목록 조회 테스트"""

    def test_get_friends_empty(self, test_session, test_user):
        """친구 없을 때 빈 목록 반환"""
        service = FriendService(test_session, test_user)
        
        friends = service.get_friends()
        
        assert friends == []

    def test_get_friends_with_friends(self, test_session, test_user, second_user):
        """친구 있을 때 목록 반환"""
        # 친구 관계 생성
        user1_service = FriendService(test_session, test_user)
        friendship = user1_service.send_friend_request(second_user.sub)
        
        user2_service = FriendService(test_session, second_user)
        user2_service.accept_friend_request(friendship.id)
        
        # user1 관점에서 친구 목록 조회
        friends = user1_service.get_friends()
        assert len(friends) == 1
        assert friends[0].user_id == second_user.sub
        
        # user2 관점에서도 친구 목록 조회
        friends = user2_service.get_friends()
        assert len(friends) == 1
        assert friends[0].user_id == test_user.sub

    def test_is_friend_true(self, test_session, test_user, second_user):
        """친구 여부 확인 - True"""
        user1_service = FriendService(test_session, test_user)
        friendship = user1_service.send_friend_request(second_user.sub)
        
        user2_service = FriendService(test_session, second_user)
        user2_service.accept_friend_request(friendship.id)
        
        assert user1_service.is_friend(second_user.sub) is True
        assert user2_service.is_friend(test_user.sub) is True

    def test_is_friend_false(self, test_session, test_user, second_user):
        """친구 여부 확인 - False (대기 중)"""
        service = FriendService(test_session, test_user)
        service.send_friend_request(second_user.sub)
        
        # 아직 수락하지 않았으므로 친구 아님
        assert service.is_friend(second_user.sub) is False


class TestBlockUser:
    """사용자 차단 테스트"""

    def test_block_user_success(self, test_session, test_user, second_user):
        """사용자 차단 성공"""
        service = FriendService(test_session, test_user)
        
        friendship = service.block_user(second_user.sub)
        
        assert friendship.status == FriendshipStatus.BLOCKED
        assert friendship.blocked_by == test_user.sub

    def test_block_existing_friend(self, test_session, test_user, second_user):
        """기존 친구 차단"""
        # 먼저 친구 관계 생성
        user1_service = FriendService(test_session, test_user)
        friendship = user1_service.send_friend_request(second_user.sub)
        
        user2_service = FriendService(test_session, second_user)
        user2_service.accept_friend_request(friendship.id)
        
        # 친구 차단
        blocked = user1_service.block_user(second_user.sub)
        
        assert blocked.status == FriendshipStatus.BLOCKED
        assert user1_service.is_friend(second_user.sub) is False

    def test_unblock_user_success(self, test_session, test_user, second_user):
        """차단 해제 성공"""
        service = FriendService(test_session, test_user)
        service.block_user(second_user.sub)
        
        service.unblock_user(second_user.sub)
        
        # 차단 해제 후 관계가 삭제됨
        assert service.has_blocked(second_user.sub) is False

    def test_send_request_to_blocked_user_fails(self, test_session, test_user, second_user):
        """차단한 사용자에게 친구 요청 실패"""
        service = FriendService(test_session, test_user)
        service.block_user(second_user.sub)
        
        # 차단한 상태에서 친구 요청 시도
        with pytest.raises(UserBlockedError):
            service.send_friend_request(second_user.sub)


class TestRemoveFriend:
    """친구 삭제 테스트"""

    def test_remove_friend_success(self, test_session, test_user, second_user):
        """친구 삭제 성공"""
        # 친구 관계 생성
        user1_service = FriendService(test_session, test_user)
        friendship = user1_service.send_friend_request(second_user.sub)
        
        user2_service = FriendService(test_session, second_user)
        user2_service.accept_friend_request(friendship.id)
        
        # 친구 삭제
        user1_service.remove_friend(friendship.id)
        
        # 삭제 후 친구 아님
        assert user1_service.is_friend(second_user.sub) is False

    def test_remove_friend_not_found(self, test_session, test_user):
        """존재하지 않는 친구 삭제 시도"""
        from uuid import uuid4
        
        service = FriendService(test_session, test_user)
        
        with pytest.raises(FriendshipNotFoundError):
            service.remove_friend(uuid4())


class TestAllowListCleanup:
    """친구 삭제/차단 시 AllowList 정리 테스트"""

    def test_remove_friend_cleans_allow_list(self, test_session, test_user, second_user):
        """친구 삭제 시 AllowList에서 상대방 제거"""
        from uuid import uuid4
        from app.domain.visibility.service import VisibilityService
        from app.domain.visibility.enums import VisibilityLevel, ResourceType
        from app.crud import visibility as visibility_crud

        # 1. 친구 관계 생성
        user1_service = FriendService(test_session, test_user)
        friendship = user1_service.send_friend_request(second_user.sub)
        
        user2_service = FriendService(test_session, second_user)
        user2_service.accept_friend_request(friendship.id)

        # 2. user1이 리소스에 SELECTED_FRIENDS로 second_user 추가
        resource_id = uuid4()
        vis_service = VisibilityService(test_session, test_user)
        visibility = vis_service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            level=VisibilityLevel.SELECTED_FRIENDS,
            allowed_user_ids=[second_user.sub],
        )

        # 3. AllowList에 있는지 확인
        assert visibility_crud.is_user_in_allow_list(
            test_session, visibility.id, second_user.sub
        ) is True

        # 4. 친구 삭제
        user1_service.remove_friend(friendship.id)

        # 5. AllowList에서 제거되었는지 확인
        assert visibility_crud.is_user_in_allow_list(
            test_session, visibility.id, second_user.sub
        ) is False

    def test_remove_friend_cleans_both_allow_lists(
        self, test_session, test_user, second_user
    ):
        """친구 삭제 시 양쪽 AllowList 모두 정리"""
        from uuid import uuid4
        from app.domain.visibility.service import VisibilityService
        from app.domain.visibility.enums import VisibilityLevel, ResourceType
        from app.crud import visibility as visibility_crud

        # 1. 친구 관계 생성
        user1_service = FriendService(test_session, test_user)
        friendship = user1_service.send_friend_request(second_user.sub)
        
        user2_service = FriendService(test_session, second_user)
        user2_service.accept_friend_request(friendship.id)

        # 2. user1이 second_user를 AllowList에 추가
        resource_id_1 = uuid4()
        vis_service_1 = VisibilityService(test_session, test_user)
        visibility_1 = vis_service_1.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id_1,
            level=VisibilityLevel.SELECTED_FRIENDS,
            allowed_user_ids=[second_user.sub],
        )

        # 3. second_user가 test_user를 AllowList에 추가
        resource_id_2 = uuid4()
        vis_service_2 = VisibilityService(test_session, second_user)
        visibility_2 = vis_service_2.set_visibility(
            resource_type=ResourceType.TIMER,
            resource_id=resource_id_2,
            level=VisibilityLevel.SELECTED_FRIENDS,
            allowed_user_ids=[test_user.sub],
        )

        # 4. 양쪽 AllowList에 있는지 확인
        assert visibility_crud.is_user_in_allow_list(
            test_session, visibility_1.id, second_user.sub
        ) is True
        assert visibility_crud.is_user_in_allow_list(
            test_session, visibility_2.id, test_user.sub
        ) is True

        # 5. 친구 삭제
        user1_service.remove_friend(friendship.id)

        # 6. 양쪽 AllowList에서 모두 제거되었는지 확인
        assert visibility_crud.is_user_in_allow_list(
            test_session, visibility_1.id, second_user.sub
        ) is False
        assert visibility_crud.is_user_in_allow_list(
            test_session, visibility_2.id, test_user.sub
        ) is False

    def test_block_friend_cleans_allow_list(self, test_session, test_user, second_user):
        """친구 차단 시 AllowList에서 상대방 제거"""
        from uuid import uuid4
        from app.domain.visibility.service import VisibilityService
        from app.domain.visibility.enums import VisibilityLevel, ResourceType
        from app.crud import visibility as visibility_crud

        # 1. 친구 관계 생성
        user1_service = FriendService(test_session, test_user)
        friendship = user1_service.send_friend_request(second_user.sub)
        
        user2_service = FriendService(test_session, second_user)
        user2_service.accept_friend_request(friendship.id)

        # 2. user1이 리소스에 SELECTED_FRIENDS로 second_user 추가
        resource_id = uuid4()
        vis_service = VisibilityService(test_session, test_user)
        visibility = vis_service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            level=VisibilityLevel.SELECTED_FRIENDS,
            allowed_user_ids=[second_user.sub],
        )

        # 3. AllowList에 있는지 확인
        assert visibility_crud.is_user_in_allow_list(
            test_session, visibility.id, second_user.sub
        ) is True

        # 4. 친구 차단
        user1_service.block_user(second_user.sub)

        # 5. AllowList에서 제거되었는지 확인
        assert visibility_crud.is_user_in_allow_list(
            test_session, visibility.id, second_user.sub
        ) is False

    def test_block_non_friend_does_not_affect_allow_list(
        self, test_session, test_user, second_user, third_user
    ):
        """친구가 아닌 사용자 차단 시 AllowList 영향 없음"""
        from uuid import uuid4
        from app.domain.visibility.service import VisibilityService
        from app.domain.visibility.enums import VisibilityLevel, ResourceType
        from app.crud import visibility as visibility_crud

        # 1. test_user와 third_user가 친구
        user1_service = FriendService(test_session, test_user)
        friendship = user1_service.send_friend_request(third_user.sub)
        
        user3_service = FriendService(test_session, third_user)
        user3_service.accept_friend_request(friendship.id)

        # 2. user1이 third_user를 AllowList에 추가
        resource_id = uuid4()
        vis_service = VisibilityService(test_session, test_user)
        visibility = vis_service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            level=VisibilityLevel.SELECTED_FRIENDS,
            allowed_user_ids=[third_user.sub],
        )

        # 3. second_user(친구 아님) 차단
        user1_service.block_user(second_user.sub)

        # 4. third_user는 여전히 AllowList에 있음
        assert visibility_crud.is_user_in_allow_list(
            test_session, visibility.id, third_user.sub
        ) is True
