"""
VisibilityService 테스트

가시성 및 접근 제어 비즈니스 로직 테스트
"""
from datetime import datetime, UTC
from uuid import uuid4

import pytest

from app.core.auth import CurrentUser
from app.domain.friend.service import FriendService
from app.domain.visibility.service import VisibilityService
from app.domain.visibility.enums import VisibilityLevel, ResourceType
from app.domain.visibility.exceptions import (
    AccessDeniedError,
    CannotShareWithNonFriendError,
)


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


@pytest.fixture
def friendship(test_session, test_user, second_user):
    """test_user와 second_user의 친구 관계"""
    user1_service = FriendService(test_session, test_user)
    friendship = user1_service.send_friend_request(second_user.sub)
    
    user2_service = FriendService(test_session, second_user)
    user2_service.accept_friend_request(friendship.id)
    
    return friendship


class TestCanAccess:
    """접근 권한 확인 테스트"""

    def test_owner_always_can_access(self, test_session, test_user):
        """소유자는 항상 접근 가능"""
        service = VisibilityService(test_session, test_user)
        resource_id = uuid4()
        
        # 가시성 설정 없이도 소유자는 접근 가능
        # (PRIVATE으로 간주되지만 소유자이므로 접근 가능)
        can_access = service.can_access(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            owner_id=test_user.sub,
        )
        
        assert can_access is True

    def test_private_denies_non_owner(self, test_session, test_user, second_user):
        """PRIVATE은 소유자만 접근 가능"""
        resource_id = uuid4()
        
        # 소유자가 가시성 설정
        owner_service = VisibilityService(test_session, test_user)
        owner_service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            level=VisibilityLevel.PRIVATE,
        )
        
        # 다른 사용자 접근 시도
        other_service = VisibilityService(test_session, second_user)
        can_access = other_service.can_access(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            owner_id=test_user.sub,
        )
        
        assert can_access is False

    def test_public_allows_everyone(self, test_session, test_user, second_user):
        """PUBLIC은 모든 사용자 접근 가능"""
        resource_id = uuid4()
        
        # 소유자가 PUBLIC으로 설정
        owner_service = VisibilityService(test_session, test_user)
        owner_service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            level=VisibilityLevel.PUBLIC,
        )
        
        # 다른 사용자 접근
        other_service = VisibilityService(test_session, second_user)
        can_access = other_service.can_access(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            owner_id=test_user.sub,
        )
        
        assert can_access is True

    def test_friends_allows_friends(
        self, test_session, test_user, second_user, friendship
    ):
        """FRIENDS는 친구만 접근 가능"""
        resource_id = uuid4()
        
        # 소유자가 FRIENDS로 설정
        owner_service = VisibilityService(test_session, test_user)
        owner_service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            level=VisibilityLevel.FRIENDS,
        )
        
        # 친구 접근
        friend_service = VisibilityService(test_session, second_user)
        can_access = friend_service.can_access(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            owner_id=test_user.sub,
        )
        
        assert can_access is True

    def test_friends_denies_non_friends(
        self, test_session, test_user, second_user, third_user, friendship
    ):
        """FRIENDS는 친구가 아닌 사용자 접근 불가"""
        resource_id = uuid4()
        
        # 소유자가 FRIENDS로 설정
        owner_service = VisibilityService(test_session, test_user)
        owner_service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            level=VisibilityLevel.FRIENDS,
        )
        
        # 친구가 아닌 사용자 접근
        non_friend_service = VisibilityService(test_session, third_user)
        can_access = non_friend_service.can_access(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            owner_id=test_user.sub,
        )
        
        assert can_access is False

    def test_selected_friends_allows_listed_friends(
        self, test_session, test_user, second_user, friendship
    ):
        """SELECTED_FRIENDS는 허용 목록의 친구만 접근 가능"""
        resource_id = uuid4()
        
        # 소유자가 SELECTED_FRIENDS로 설정하고 second_user 허용
        owner_service = VisibilityService(test_session, test_user)
        owner_service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            level=VisibilityLevel.SELECTED_FRIENDS,
            allowed_user_ids=[second_user.sub],
        )
        
        # 허용된 친구 접근
        friend_service = VisibilityService(test_session, second_user)
        can_access = friend_service.can_access(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            owner_id=test_user.sub,
        )
        
        assert can_access is True

    def test_selected_friends_denies_unlisted_friends(
        self, test_session, test_user, second_user, third_user
    ):
        """SELECTED_FRIENDS는 허용 목록에 없는 친구 접근 불가"""
        resource_id = uuid4()
        
        # third_user와도 친구 관계 생성
        user1_service = FriendService(test_session, test_user)
        friendship = user1_service.send_friend_request(third_user.sub)
        
        user3_service = FriendService(test_session, third_user)
        user3_service.accept_friend_request(friendship.id)
        
        # 소유자가 SELECTED_FRIENDS로 설정 (second_user만 허용, third_user는 미허용)
        owner_service = VisibilityService(test_session, test_user)
        # 먼저 second_user와 친구 되어야 함
        user1_service = FriendService(test_session, test_user)
        friendship2 = user1_service.send_friend_request(second_user.sub)
        
        user2_service = FriendService(test_session, second_user)
        user2_service.accept_friend_request(friendship2.id)
        
        owner_service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            level=VisibilityLevel.SELECTED_FRIENDS,
            allowed_user_ids=[second_user.sub],
        )
        
        # 허용되지 않은 친구 접근
        unlisted_service = VisibilityService(test_session, third_user)
        can_access = unlisted_service.can_access(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            owner_id=test_user.sub,
        )
        
        assert can_access is False


class TestRequireAccess:
    """접근 권한 강제 테스트"""

    def test_require_access_passes_for_owner(self, test_session, test_user):
        """소유자는 require_access 통과"""
        service = VisibilityService(test_session, test_user)
        resource_id = uuid4()
        
        # 예외가 발생하지 않아야 함
        service.require_access(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            owner_id=test_user.sub,
        )

    def test_require_access_raises_for_denied(self, test_session, test_user, second_user):
        """접근 거부 시 AccessDeniedError 발생"""
        resource_id = uuid4()
        
        # 가시성 설정 없음 (PRIVATE으로 간주)
        other_service = VisibilityService(test_session, second_user)
        
        with pytest.raises(AccessDeniedError):
            other_service.require_access(
                resource_type=ResourceType.SCHEDULE,
                resource_id=resource_id,
                owner_id=test_user.sub,
            )


class TestSetVisibility:
    """가시성 설정 테스트"""

    def test_set_visibility_creates_new(self, test_session, test_user):
        """새 가시성 설정 생성"""
        service = VisibilityService(test_session, test_user)
        resource_id = uuid4()
        
        visibility = service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            level=VisibilityLevel.FRIENDS,
        )
        
        assert visibility is not None
        assert visibility.level == VisibilityLevel.FRIENDS

    def test_set_visibility_updates_existing(self, test_session, test_user):
        """기존 가시성 설정 업데이트"""
        service = VisibilityService(test_session, test_user)
        resource_id = uuid4()
        
        # 초기 설정
        service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            level=VisibilityLevel.PRIVATE,
        )
        
        # 업데이트
        visibility = service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            level=VisibilityLevel.PUBLIC,
        )
        
        assert visibility.level == VisibilityLevel.PUBLIC

    def test_set_visibility_with_non_friend_fails(
        self, test_session, test_user, second_user
    ):
        """친구가 아닌 사용자를 SELECTED_FRIENDS에 추가 시 실패"""
        service = VisibilityService(test_session, test_user)
        resource_id = uuid4()
        
        # 친구가 아닌 사용자를 허용 목록에 추가 시도
        with pytest.raises(CannotShareWithNonFriendError):
            service.set_visibility(
                resource_type=ResourceType.SCHEDULE,
                resource_id=resource_id,
                level=VisibilityLevel.SELECTED_FRIENDS,
                allowed_user_ids=[second_user.sub],
            )


class TestGetVisibility:
    """가시성 조회 테스트"""

    def test_get_visibility_returns_none_if_not_set(self, test_session, test_user):
        """가시성 미설정 시 None 반환"""
        service = VisibilityService(test_session, test_user)
        resource_id = uuid4()
        
        visibility = service.get_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
        )
        
        assert visibility is None

    def test_get_visibility_returns_settings(self, test_session, test_user, second_user):
        """가시성 설정 조회"""
        # 친구 관계 생성
        user1_service = FriendService(test_session, test_user)
        friendship = user1_service.send_friend_request(second_user.sub)
        
        user2_service = FriendService(test_session, second_user)
        user2_service.accept_friend_request(friendship.id)
        
        service = VisibilityService(test_session, test_user)
        resource_id = uuid4()
        
        # 가시성 설정
        service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            level=VisibilityLevel.SELECTED_FRIENDS,
            allowed_user_ids=[second_user.sub],
        )
        
        # 조회
        visibility = service.get_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
        )
        
        assert visibility is not None
        assert visibility.level == VisibilityLevel.SELECTED_FRIENDS
        assert second_user.sub in visibility.allowed_user_ids


class TestDeleteVisibility:
    """가시성 삭제 테스트"""

    def test_delete_visibility_success(self, test_session, test_user):
        """가시성 삭제 성공"""
        service = VisibilityService(test_session, test_user)
        resource_id = uuid4()
        
        # 설정
        service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            level=VisibilityLevel.PUBLIC,
        )
        
        # 삭제
        result = service.delete_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
        )
        
        assert result is True
        
        # 삭제 후 조회
        visibility = service.get_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
        )
        assert visibility is None

    def test_delete_visibility_not_found(self, test_session, test_user):
        """존재하지 않는 가시성 삭제"""
        service = VisibilityService(test_session, test_user)
        
        result = service.delete_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=uuid4(),
        )
        
        assert result is False
