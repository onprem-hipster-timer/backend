"""
연결 타이머 처리 정책 테스트 (app/domain/timer/event_handlers.py)

Todo·Schedule을 지우면 연결 타이머를 클라이언트가 지정한 linked_timer_policy로 처리한다.
연결 타이머가 있는데 정책이 없으면 422(LinkedTimerPolicyRequiredError)이고 전체가 rollback된다.
실시간 이벤트는 커밋된 뒤에만 sink로 넘어가므로 실제로 커밋하는 세션을 쓴다.
"""
from uuid import UUID

import pytest
from sqlmodel import Session

from app.core.constants import TimerStatus
from app.crud import visibility as visibility_crud
from app.domain.friend.service import FriendService
from app.domain.tag.schema.dto import TagGroupCreate
from app.domain.tag.service import TagService
from app.domain.timer.enums import LinkedTimerPolicy
from app.domain.timer.exceptions import LinkedTimerPolicyRequiredError
from app.domain.timer.model import TimerSession
from app.domain.timer.schema.dto import TimerCreate
from app.domain.timer.service import TimerService
from app.domain.todo.model import Todo
from app.domain.todo.schema.dto import TodoCreate
from app.domain.todo.service import TodoService
from app.domain.user.service import UserProfileService
from app.domain.visibility.enums import ResourceType, VisibilityLevel
from app.domain.visibility.service import VisibilityService
from tests.conftest import make_user

OWNER = make_user("owner", name="Owner Name")
FRIEND = make_user("friend")


@pytest.fixture
def session(test_engine):
    with Session(test_engine) as session:
        # 실시간 이벤트의 actor_name은 프로필 캐시(요청마다 JWT name으로 동기화)에서 온다
        UserProfileService(session, OWNER).sync_from_current_user()
        session.commit()
        yield session


@pytest.fixture
def group_id(session) -> UUID:
    group = TagService(session, OWNER).create_tag_group(TagGroupCreate(name="그룹", color="#FF5733"))
    session.commit()
    return group.id


def _todo(session, group_id, **fields) -> Todo:
    todo = TodoService(session, OWNER).create_todo(TodoCreate(title="할 일", tag_group_id=group_id, **fields))
    session.commit()
    return todo


def _timer(session, **links) -> TimerSession:
    timer = TimerService(session, OWNER).create_timer(TimerCreate(allocated_duration=1800, **links))
    session.commit()
    return timer


def _stored(test_engine, timer_id: UUID) -> TimerSession | None:
    with Session(test_engine) as fresh:
        return fresh.get(TimerSession, timer_id)


# ============================================================
# Todo 삭제
# ============================================================

class TestDeleteTodo:
    def test_without_policy_rejected_and_rolled_back(self, session, test_engine, group_id, after_commit_items):
        todo = _todo(session, group_id)
        timer = _timer(session, todo_id=todo.id)
        after_commit_items.clear()

        with pytest.raises(LinkedTimerPolicyRequiredError) as exc_info:
            TodoService(session, OWNER).delete_todo(todo.id)
        session.rollback()

        assert exc_info.value.status_code == 422
        with Session(test_engine) as fresh:
            assert fresh.get(Todo, todo.id) is not None
        assert _stored(test_engine, timer.id).todo_id == todo.id
        assert after_commit_items == []

    def test_unlink_keeps_timer_without_todo(self, session, test_engine, group_id, after_commit_items):
        todo = _todo(session, group_id)
        timer = _timer(session, todo_id=todo.id)
        before = timer.updated_at
        after_commit_items.clear()

        TodoService(session, OWNER).delete_todo(todo.id, linked_timer_policy=LinkedTimerPolicy.UNLINK)
        session.commit()

        stored = _stored(test_engine, timer.id)
        assert stored.todo_id is None
        assert stored.updated_at > before
        [item] = after_commit_items
        assert item["users"] == {OWNER.sub}
        message = item["message"]
        assert message["type"] == "timer.updated"
        assert message["from_user"] == OWNER.sub
        assert message["payload"]["action"] == "update"
        assert message["payload"]["actor_name"] == "Owner Name"
        assert message["payload"]["timer"]["id"] == str(timer.id)
        assert message["payload"]["timer"]["todo_id"] is None

    @pytest.mark.parametrize("pause, status", [(False, TimerStatus.RUNNING), (True, TimerStatus.PAUSED)])
    def test_unlink_keeps_active_timer_running(self, session, test_engine, group_id, pause, status):
        todo = _todo(session, group_id)
        timer = _timer(session, todo_id=todo.id)
        if pause:
            TimerService(session, OWNER).pause_timer(timer.id)
            session.commit()

        TodoService(session, OWNER).delete_todo(todo.id, linked_timer_policy=LinkedTimerPolicy.UNLINK)
        session.commit()

        assert _stored(test_engine, timer.id).status == status

    def test_delete_removes_timer_and_visibility(self, session, test_engine, group_id, after_commit_items):
        request = FriendService(session, OWNER).send_friend_request(FRIEND.sub)
        FriendService(session, FRIEND).accept_friend_request(request.id)
        todo = _todo(session, group_id)
        timer = _timer(session, todo_id=todo.id)
        timer_id = timer.id
        VisibilityService(session, OWNER).set_visibility(ResourceType.TIMER, timer_id, VisibilityLevel.FRIENDS)
        session.commit()
        after_commit_items.clear()

        TodoService(session, OWNER).delete_todo(todo.id, linked_timer_policy=LinkedTimerPolicy.DELETE)
        session.commit()

        assert _stored(test_engine, timer_id) is None
        assert visibility_crud.get_visibility_by_resource(session, ResourceType.TIMER, timer_id) is None
        [item] = after_commit_items
        # 받는 사람은 공개 범위 설정을 지우기 전에 계산한다
        assert item["users"] == {OWNER.sub, FRIEND.sub}
        message = item["message"]
        assert message["type"] == "timer.deleted"
        assert message["payload"]["action"] == "delete"
        assert message["payload"]["timer"] is None
        assert message["payload"]["timer_id"] == str(timer_id)
