"""
VisibilityService 테스트

가시성 및 접근 제어 비즈니스 로직 테스트
"""
from uuid import uuid4

import pytest

from app.core.auth import CurrentUser
from app.domain.friend.service import FriendService
from app.domain.visibility.enums import VisibilityLevel, ResourceType
from app.domain.visibility.exceptions import (
    AccessDeniedError,
    CannotShareWithNonFriendError,
)
from app.domain.visibility.service import VisibilityService


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

    def test_allowed_emails_allows_specific_email(
            self, test_session, test_user, second_user
    ):
        """ALLOWED_EMAILS는 허용된 특정 이메일만 접근 가능"""
        resource_id = uuid4()

        # 소유자가 ALLOWED_EMAILS로 설정하고 특정 이메일 허용
        owner_service = VisibilityService(test_session, test_user)
        owner_service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            level=VisibilityLevel.ALLOWED_EMAILS,
            allowed_emails=[second_user.email],
        )

        # 허용된 이메일 사용자 접근
        allowed_service = VisibilityService(test_session, second_user)
        can_access = allowed_service.can_access(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            owner_id=test_user.sub,
        )

        assert can_access is True

    def test_allowed_emails_denies_non_allowed_email(
            self, test_session, test_user, second_user, third_user
    ):
        """ALLOWED_EMAILS는 허용되지 않은 이메일 접근 불가"""
        resource_id = uuid4()

        # 소유자가 ALLOWED_EMAILS로 설정 (second_user만 허용)
        owner_service = VisibilityService(test_session, test_user)
        owner_service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            level=VisibilityLevel.ALLOWED_EMAILS,
            allowed_emails=[second_user.email],
        )

        # 허용되지 않은 이메일 사용자 접근
        non_allowed_service = VisibilityService(test_session, third_user)
        can_access = non_allowed_service.can_access(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            owner_id=test_user.sub,
        )

        assert can_access is False

    def test_allowed_emails_allows_domain(
            self, test_session, test_user, second_user
    ):
        """ALLOWED_EMAILS는 허용된 도메인의 모든 이메일 접근 가능"""
        resource_id = uuid4()

        # second_user의 이메일이 "second@example.com"이므로 "example.com" 도메인 허용
        owner_service = VisibilityService(test_session, test_user)
        owner_service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            level=VisibilityLevel.ALLOWED_EMAILS,
            allowed_domains=["example.com"],
        )

        # 허용된 도메인 사용자 접근
        allowed_service = VisibilityService(test_session, second_user)
        can_access = allowed_service.can_access(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            owner_id=test_user.sub,
        )

        assert can_access is True

    def test_allowed_emails_denies_non_allowed_domain(
            self, test_session, test_user, second_user
    ):
        """ALLOWED_EMAILS는 허용되지 않은 도메인 접근 불가"""
        resource_id = uuid4()

        # "company.com" 도메인만 허용 (second_user는 "example.com")
        owner_service = VisibilityService(test_session, test_user)
        owner_service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            level=VisibilityLevel.ALLOWED_EMAILS,
            allowed_domains=["company.com"],
        )

        # 허용되지 않은 도메인 사용자 접근
        non_allowed_service = VisibilityService(test_session, second_user)
        can_access = non_allowed_service.can_access(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            owner_id=test_user.sub,
        )

        assert can_access is False

    def test_allowed_emails_denies_user_without_email(
            self, test_session, test_user, second_user
    ):
        """ALLOWED_EMAILS는 이메일이 없는 사용자 접근 불가"""
        resource_id = uuid4()

        # 소유자가 ALLOWED_EMAILS로 설정
        owner_service = VisibilityService(test_session, test_user)
        owner_service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            level=VisibilityLevel.ALLOWED_EMAILS,
            allowed_emails=[second_user.email],
        )

        # 이메일이 없는 사용자 생성
        user_without_email = CurrentUser(
            sub="no-email-user-id",
            email=None,
            name="No Email User",
        )

        # 이메일이 없는 사용자 접근
        no_email_service = VisibilityService(test_session, user_without_email)
        can_access = no_email_service.can_access(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            owner_id=test_user.sub,
        )

        assert can_access is False

    def test_allowed_emails_with_both_email_and_domain(
            self, test_session, test_user, second_user, third_user
    ):
        """ALLOWED_EMAILS에서 이메일과 도메인 모두로 허용"""
        resource_id = uuid4()

        # 특정 이메일 + 도메인 모두 허용
        owner_service = VisibilityService(test_session, test_user)
        owner_service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            level=VisibilityLevel.ALLOWED_EMAILS,
            allowed_emails=["specific@other.com"],
            allowed_domains=["example.com"],
        )

        # second_user (example.com 도메인) - 도메인으로 허용
        allowed_service = VisibilityService(test_session, second_user)
        can_access = allowed_service.can_access(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            owner_id=test_user.sub,
        )
        assert can_access is True

        # 특정 이메일 사용자
        specific_user = CurrentUser(
            sub="specific-user-id",
            email="specific@other.com",
            name="Specific User",
        )
        specific_service = VisibilityService(test_session, specific_user)
        can_access = specific_service.can_access(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            owner_id=test_user.sub,
        )
        assert can_access is True

        # 허용되지 않은 사용자
        non_allowed_user = CurrentUser(
            sub="non-allowed-user-id",
            email="random@random.com",
            name="Random User",
        )
        non_allowed_service = VisibilityService(test_session, non_allowed_user)
        can_access = non_allowed_service.can_access(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            owner_id=test_user.sub,
        )
        assert can_access is False

    def test_allowed_emails_multiple_domains(
            self, test_session, test_user
    ):
        """ALLOWED_EMAILS에서 여러 도메인 허용"""
        resource_id = uuid4()

        owner_service = VisibilityService(test_session, test_user)
        owner_service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            level=VisibilityLevel.ALLOWED_EMAILS,
            allowed_domains=["company.com", "partner.org", "vendor.net"],
        )

        # company.com 도메인 사용자
        company_user = CurrentUser(sub="company-user", email="alice@company.com", name="Alice")
        company_service = VisibilityService(test_session, company_user)
        assert company_service.can_access(ResourceType.SCHEDULE, resource_id, test_user.sub) is True

        # partner.org 도메인 사용자
        partner_user = CurrentUser(sub="partner-user", email="bob@partner.org", name="Bob")
        partner_service = VisibilityService(test_session, partner_user)
        assert partner_service.can_access(ResourceType.SCHEDULE, resource_id, test_user.sub) is True

        # vendor.net 도메인 사용자
        vendor_user = CurrentUser(sub="vendor-user", email="charlie@vendor.net", name="Charlie")
        vendor_service = VisibilityService(test_session, vendor_user)
        assert vendor_service.can_access(ResourceType.SCHEDULE, resource_id, test_user.sub) is True

        # 허용되지 않은 도메인 사용자
        other_user = CurrentUser(sub="other-user", email="dave@other.com", name="Dave")
        other_service = VisibilityService(test_session, other_user)
        assert other_service.can_access(ResourceType.SCHEDULE, resource_id, test_user.sub) is False

    def test_allowed_emails_multiple_emails(
            self, test_session, test_user
    ):
        """ALLOWED_EMAILS에서 여러 이메일 허용"""
        resource_id = uuid4()

        owner_service = VisibilityService(test_session, test_user)
        owner_service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            level=VisibilityLevel.ALLOWED_EMAILS,
            allowed_emails=["alice@example.com", "bob@example.com", "charlie@different.com"],
        )

        # 허용된 이메일 사용자들
        alice = CurrentUser(sub="alice-user", email="alice@example.com", name="Alice")
        alice_service = VisibilityService(test_session, alice)
        assert alice_service.can_access(ResourceType.SCHEDULE, resource_id, test_user.sub) is True

        bob = CurrentUser(sub="bob-user", email="bob@example.com", name="Bob")
        bob_service = VisibilityService(test_session, bob)
        assert bob_service.can_access(ResourceType.SCHEDULE, resource_id, test_user.sub) is True

        charlie = CurrentUser(sub="charlie-user", email="charlie@different.com", name="Charlie")
        charlie_service = VisibilityService(test_session, charlie)
        assert charlie_service.can_access(ResourceType.SCHEDULE, resource_id, test_user.sub) is True

        # 허용되지 않은 이메일
        dave = CurrentUser(sub="dave-user", email="dave@example.com", name="Dave")
        dave_service = VisibilityService(test_session, dave)
        assert dave_service.can_access(ResourceType.SCHEDULE, resource_id, test_user.sub) is False

    def test_allowed_emails_empty_list_denies_all(
            self, test_session, test_user, second_user
    ):
        """ALLOWED_EMAILS에 빈 목록 시 아무도 접근 불가"""
        resource_id = uuid4()

        owner_service = VisibilityService(test_session, test_user)
        owner_service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            level=VisibilityLevel.ALLOWED_EMAILS,
            # 이메일/도메인 없이 설정
        )

        # 다른 사용자 접근 불가
        other_service = VisibilityService(test_session, second_user)
        can_access = other_service.can_access(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            owner_id=test_user.sub,
        )
        assert can_access is False

    def test_allowed_emails_subdomain_not_matched(
            self, test_session, test_user
    ):
        """ALLOWED_EMAILS에서 서브도메인은 정확히 매칭되어야 함"""
        resource_id = uuid4()

        owner_service = VisibilityService(test_session, test_user)
        owner_service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            level=VisibilityLevel.ALLOWED_EMAILS,
            allowed_domains=["example.com"],  # example.com만 허용
        )

        # 정확히 example.com 도메인 - 허용
        exact_user = CurrentUser(sub="exact-user", email="user@example.com", name="Exact User")
        exact_service = VisibilityService(test_session, exact_user)
        assert exact_service.can_access(ResourceType.SCHEDULE, resource_id, test_user.sub) is True

        # 서브도메인 sub.example.com - 불허용 (정확한 매칭만 지원)
        subdomain_user = CurrentUser(sub="subdomain-user", email="user@sub.example.com", name="Subdomain User")
        subdomain_service = VisibilityService(test_session, subdomain_user)
        assert subdomain_service.can_access(ResourceType.SCHEDULE, resource_id, test_user.sub) is False

    def test_allowed_emails_owner_always_has_access(
            self, test_session, test_user, second_user
    ):
        """ALLOWED_EMAILS 설정해도 소유자는 항상 접근 가능"""
        resource_id = uuid4()

        owner_service = VisibilityService(test_session, test_user)
        owner_service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            level=VisibilityLevel.ALLOWED_EMAILS,
            allowed_emails=[second_user.email],  # 소유자 이메일은 목록에 없음
        )

        # 소유자 접근 - 항상 허용
        can_access = owner_service.can_access(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            owner_id=test_user.sub,
        )
        assert can_access is True


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

    def test_set_visibility_with_allowed_emails_creates_new(
            self, test_session, test_user, second_user
    ):
        """ALLOWED_EMAILS 레벨로 가시성 설정 생성"""
        service = VisibilityService(test_session, test_user)
        resource_id = uuid4()

        visibility = service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            level=VisibilityLevel.ALLOWED_EMAILS,
            allowed_emails=[second_user.email],
            allowed_domains=["example.com"],
        )

        assert visibility is not None
        assert visibility.level == VisibilityLevel.ALLOWED_EMAILS

    def test_set_visibility_updates_allowed_emails(
            self, test_session, test_user, second_user, third_user
    ):
        """ALLOWED_EMAILS 레벨 가시성 설정 업데이트"""
        service = VisibilityService(test_session, test_user)
        resource_id = uuid4()

        # 초기 설정
        service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            level=VisibilityLevel.ALLOWED_EMAILS,
            allowed_emails=[second_user.email],
        )

        # 업데이트 (새 이메일 추가)
        visibility = service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            level=VisibilityLevel.ALLOWED_EMAILS,
            allowed_emails=[second_user.email, third_user.email],
            allowed_domains=["example.com"],
        )

        assert visibility.level == VisibilityLevel.ALLOWED_EMAILS

        # 조회하여 확인
        visibility_read = service.get_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
        )
        assert second_user.email in visibility_read.allowed_emails
        assert third_user.email in visibility_read.allowed_emails
        assert "example.com" in visibility_read.allowed_domains

    def test_changing_from_allowed_emails_clears_email_list(
            self, test_session, test_user, second_user
    ):
        """ALLOWED_EMAILS에서 다른 레벨로 변경 시 이메일 목록 삭제"""
        service = VisibilityService(test_session, test_user)
        resource_id = uuid4()

        # ALLOWED_EMAILS로 설정
        service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            level=VisibilityLevel.ALLOWED_EMAILS,
            allowed_emails=[second_user.email],
            allowed_domains=["example.com"],
        )

        # PUBLIC으로 변경
        service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            level=VisibilityLevel.PUBLIC,
        )

        # 다시 ALLOWED_EMAILS로 변경 (이메일 목록은 비어있어야 함)
        service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            level=VisibilityLevel.ALLOWED_EMAILS,
            # 새 목록 없이 설정
        )

        # second_user 접근 불가 (이전 목록이 삭제되었으므로)
        other_service = VisibilityService(test_session, second_user)
        can_access = other_service.can_access(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            owner_id=test_user.sub,
        )
        assert can_access is False

    def test_allowed_emails_update_removes_old_and_adds_new(
            self, test_session, test_user
    ):
        """ALLOWED_EMAILS 업데이트 시 기존 목록을 새 목록으로 교체"""
        service = VisibilityService(test_session, test_user)
        resource_id = uuid4()

        # 초기 설정
        service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            level=VisibilityLevel.ALLOWED_EMAILS,
            allowed_emails=["old@example.com"],
            allowed_domains=["old-domain.com"],
        )

        # 이전 사용자 접근 가능
        old_user = CurrentUser(sub="old-user", email="old@example.com", name="Old User")
        old_service = VisibilityService(test_session, old_user)
        assert old_service.can_access(ResourceType.SCHEDULE, resource_id, test_user.sub) is True

        # 새 목록으로 업데이트 (old@example.com 제외)
        service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            level=VisibilityLevel.ALLOWED_EMAILS,
            allowed_emails=["new@example.com"],
            allowed_domains=["new-domain.com"],
        )

        # 이전 사용자 접근 불가
        assert old_service.can_access(ResourceType.SCHEDULE, resource_id, test_user.sub) is False

        # 새 사용자 접근 가능
        new_user = CurrentUser(sub="new-user", email="new@example.com", name="New User")
        new_service = VisibilityService(test_session, new_user)
        assert new_service.can_access(ResourceType.SCHEDULE, resource_id, test_user.sub) is True


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

    def test_get_visibility_returns_allowed_emails_settings(
            self, test_session, test_user, second_user
    ):
        """ALLOWED_EMAILS 가시성 설정 조회"""
        service = VisibilityService(test_session, test_user)
        resource_id = uuid4()

        # 가시성 설정 (이메일과 도메인 모두)
        service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
            level=VisibilityLevel.ALLOWED_EMAILS,
            allowed_emails=[second_user.email, "admin@company.com"],
            allowed_domains=["company.com"],
        )

        # 조회
        visibility = service.get_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=resource_id,
        )

        assert visibility is not None
        assert visibility.level == VisibilityLevel.ALLOWED_EMAILS
        assert second_user.email in visibility.allowed_emails
        assert "admin@company.com" in visibility.allowed_emails
        assert "company.com" in visibility.allowed_domains


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
