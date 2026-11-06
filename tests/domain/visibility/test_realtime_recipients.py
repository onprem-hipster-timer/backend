"""
VisibilityService.get_realtime_recipients 테스트

수신자는 소유자를 뺀, can_access가 허용하는 소유자의 친구다. 후보마다 그 사용자로
VisibilityService를 만들어 can_access를 계산한 결과와 비교한다.
"""
from uuid import uuid4

import pytest

from app.domain.friend.service import FriendService
from app.domain.visibility.enums import ResourceType, VisibilityLevel
from app.domain.visibility.service import VisibilityService
from tests.conftest import make_user

OWNER = make_user("owner")
FRIEND_A = make_user("friend-a")
FRIEND_B = make_user("friend-b")
STRANGER = make_user("stranger", email="stranger@allowed.example")
BLOCKED = make_user("blocked")
PENDING = make_user("pending")
CANDIDATES = [FRIEND_A, FRIEND_B, STRANGER, BLOCKED, PENDING]


@pytest.fixture
def relations(test_session):
    """owner의 친구 friend-a·friend-b, 차단 blocked, 수락 안 한 요청 pending"""
    owner_friends = FriendService(test_session, OWNER)
    for friend in (FRIEND_A, FRIEND_B, BLOCKED):
        request = owner_friends.send_friend_request(friend.sub)
        FriendService(test_session, friend).accept_friend_request(request.id)
    owner_friends.block_user(BLOCKED.sub)
    owner_friends.send_friend_request(PENDING.sub)
    test_session.flush()


def _accessible(session, resource_id) -> set[str]:
    return {
        user.sub
        for user in CANDIDATES
        if VisibilityService(session, user).can_access(ResourceType.TIMER, resource_id, OWNER.sub)
    }


def _recipients(session, resource_id) -> set[str]:
    return VisibilityService(session, OWNER).get_realtime_recipients(
        ResourceType.TIMER, resource_id, OWNER.sub
    )


def test_no_visibility_row_has_no_recipients(test_session, relations):
    resource_id = uuid4()

    assert _recipients(test_session, resource_id) == set()
    assert _accessible(test_session, resource_id) == set()


@pytest.mark.parametrize("level, kwargs, expected", [
    (VisibilityLevel.PRIVATE, {}, set()),
    (VisibilityLevel.FRIENDS, {}, {"friend-a", "friend-b"}),
    (VisibilityLevel.PUBLIC, {}, {"friend-a", "friend-b"}),
    (VisibilityLevel.SELECTED_FRIENDS, {"allowed_user_ids": ["friend-b"]}, {"friend-b"}),
    (VisibilityLevel.SELECTED_FRIENDS, {}, set()),
    (VisibilityLevel.ALLOWED_EMAILS, {"allowed_emails": ["friend-a@example.com"]}, set()),
    (VisibilityLevel.ALLOWED_EMAILS, {"allowed_domains": ["allowed.example"]}, set()),
])
def test_recipients_are_friends_who_can_access(test_session, relations, level, kwargs, expected):
    resource_id = uuid4()
    VisibilityService(test_session, OWNER).set_visibility(ResourceType.TIMER, resource_id, level, **kwargs)

    recipients = _recipients(test_session, resource_id)

    assert recipients == expected
    assert recipients <= _accessible(test_session, resource_id)
    assert OWNER.sub not in recipients


@pytest.mark.parametrize("level", [VisibilityLevel.FRIENDS, VisibilityLevel.PUBLIC])
def test_friend_level_recipients_equal_accessible_friends(test_session, relations, level):
    """FRIENDS·PUBLIC은 접근 가능한 친구 전원에게 간다 (비친구는 PUBLIC이어도 받지 않는다)"""
    resource_id = uuid4()
    VisibilityService(test_session, OWNER).set_visibility(ResourceType.TIMER, resource_id, level)
    friends = {FRIEND_A.sub, FRIEND_B.sub}

    assert _recipients(test_session, resource_id) == _accessible(test_session, resource_id) & friends
