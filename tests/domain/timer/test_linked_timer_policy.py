"""
연결 타이머 처리 정책 테스트 (app/domain/timer/event_handlers.py)

Todo·Schedule을 지우면 연결 타이머를 클라이언트가 지정한 linked_timer_policy로 처리한다.
연결 타이머가 있는데 정책이 없으면 422(LinkedTimerPolicyRequiredError)이고 전체가 rollback된다.
실시간 이벤트는 커밋된 뒤에만 sink로 넘어가므로 실제로 커밋하는 세션을 쓴다.
"""
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlmodel import Session

from app.core.constants import TimerStatus
from app.crud import schedule as schedule_crud
from app.crud import visibility as visibility_crud
from app.domain.friend.service import FriendService
from app.domain.schedule.enums import SourceTodoPolicy
from app.domain.schedule.model import Schedule
from app.domain.schedule.schema.dto import ScheduleCreate
from app.domain.schedule.service import ScheduleService
from app.domain.timer.enums import LinkedTimerPolicy
from app.domain.timer.exceptions import LinkedTimerPolicyRequiredError
from app.domain.timer.model import TimerSession
from app.domain.timer.schema.dto import TimerCreate, TimerUpdate
from app.domain.timer.service import TimerService
from app.domain.todo.enums import LinkedSchedulePolicy
from app.domain.todo.model import Todo
from app.domain.todo.schema.dto import TodoCreate, TodoUpdate
from app.domain.todo.service import TodoService
from app.domain.todo_group.schema.dto import TodoGroupCreate
from app.domain.todo_group.service import TodoGroupService
from app.domain.user.service import UserProfileService
from app.domain.visibility.enums import ResourceType, VisibilityLevel
from app.domain.visibility.service import VisibilityService
from tests.conftest import make_user

OWNER = make_user("owner", name="Owner Name")
FRIEND = make_user("friend")
START = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def session(test_engine):
    with Session(test_engine) as session:
        # 실시간 이벤트의 actor_name은 프로필 캐시(요청마다 JWT name으로 동기화)에서 온다
        UserProfileService(session, OWNER).sync_from_current_user()
        session.commit()
        yield session


@pytest.fixture
def group_id(session) -> UUID:
    group = TodoGroupService(session, OWNER).create_todo_group(TodoGroupCreate(name="그룹", color="#FF5733"))
    session.commit()
    return group.id


def _todo(session, group_id, **fields) -> Todo:
    todo = TodoService(session, OWNER).create_todo(TodoCreate(title="할 일", todo_group_id=group_id, **fields))
    session.commit()
    return todo


def _timer(session, **links) -> TimerSession:
    timer = TimerService(session, OWNER).create_timer(TimerCreate(allocated_duration=1800, **links))
    session.commit()
    return timer


def _schedule(session, **fields) -> Schedule:
    schedule = ScheduleService(session, OWNER).create_schedule(
        ScheduleCreate(title="일정", start_time=START, end_time=START + timedelta(hours=1), **fields)
    )
    session.commit()
    return schedule


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

    def test_unlink_two_timers_each_get_an_event(self, session, test_engine, group_id, after_commit_items):
        todo = _todo(session, group_id)
        first = _timer(session, todo_id=todo.id)
        second = _timer(session, todo_id=todo.id)
        after_commit_items.clear()

        TodoService(session, OWNER).delete_todo(todo.id, linked_timer_policy=LinkedTimerPolicy.UNLINK)
        session.commit()

        ids = sorted(item["message"]["payload"]["timer"]["id"] for item in after_commit_items)
        assert ids == sorted([str(first.id), str(second.id)])
        assert _stored(test_engine, first.id).todo_id is None
        assert _stored(test_engine, second.id).todo_id is None

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


# ============================================================
# Schedule 삭제
# ============================================================

class TestDeleteSchedule:
    def test_without_policy_rejected_and_rolled_back(self, session, test_engine, after_commit_items):
        schedule = _schedule(session)
        timer = _timer(session, schedule_id=schedule.id)
        after_commit_items.clear()

        with pytest.raises(LinkedTimerPolicyRequiredError):
            ScheduleService(session, OWNER).delete_schedule(schedule.id)
        session.rollback()

        with Session(test_engine) as fresh:
            assert fresh.get(Schedule, schedule.id) is not None
        assert _stored(test_engine, timer.id).schedule_id == schedule.id
        assert after_commit_items == []

    def test_unlink_keeps_timer_and_its_todo_link(self, session, test_engine, group_id, after_commit_items):
        todo = _todo(session, group_id, deadline=START)
        timer = _timer(session, todo_id=todo.id)  # 투영 일정이 함께 연결된다
        projection_id = timer.schedule_id
        assert projection_id is not None
        before = timer.updated_at
        after_commit_items.clear()

        ScheduleService(session, OWNER).delete_schedule(
            projection_id, SourceTodoPolicy.KEEP_DEADLINE, LinkedTimerPolicy.UNLINK
        )
        session.commit()

        stored = _stored(test_engine, timer.id)
        assert stored.schedule_id is None
        assert stored.todo_id == todo.id
        assert stored.status == TimerStatus.RUNNING
        assert stored.updated_at > before
        [item] = after_commit_items
        message = item["message"]
        assert message["type"] == "timer.updated"
        assert message["payload"]["action"] == "update"
        assert message["payload"]["timer"]["schedule_id"] is None
        assert message["payload"]["timer"]["todo_id"] == str(todo.id)

    def test_delete_removes_timer_and_visibility(self, session, test_engine, after_commit_items):
        schedule = _schedule(session)
        timer = _timer(session, schedule_id=schedule.id)
        timer_id = timer.id
        VisibilityService(session, OWNER).set_visibility(ResourceType.TIMER, timer_id, VisibilityLevel.PUBLIC)
        session.commit()
        after_commit_items.clear()

        ScheduleService(session, OWNER).delete_schedule(schedule.id, linked_timer_policy=LinkedTimerPolicy.DELETE)
        session.commit()

        assert _stored(test_engine, timer_id) is None
        assert visibility_crud.get_visibility_by_resource(session, ResourceType.TIMER, timer_id) is None
        [item] = after_commit_items
        assert item["message"]["type"] == "timer.deleted"
        assert item["message"]["payload"]["timer_id"] == str(timer_id)


class TestRecurringSeriesExhausted:
    """마지막 인스턴스 삭제로 원본이 지워지는 경로 — 묻지 않고 unlink, 명시하면 그 정책"""

    def _single_instance_series(self, session) -> Schedule:
        return _schedule(session, recurrence_rule="FREQ=DAILY", recurrence_end=START + timedelta(hours=1))

    def test_without_policy_unlinks_timer(self, session, test_engine, after_commit_items):
        series = self._single_instance_series(session)
        timer = _timer(session, schedule_id=series.id)
        after_commit_items.clear()

        ScheduleService(session, OWNER).delete_recurring_instance(series.id, START)
        session.commit()

        with Session(test_engine) as fresh:
            assert fresh.get(Schedule, series.id) is None
        assert _stored(test_engine, timer.id).schedule_id is None
        assert [item["message"]["type"] for item in after_commit_items] == ["timer.updated"]

    def test_explicit_delete_policy_deletes_timer(self, session, test_engine, after_commit_items):
        series = self._single_instance_series(session)
        timer = _timer(session, schedule_id=series.id)
        after_commit_items.clear()

        ScheduleService(session, OWNER).delete_recurring_instance(
            series.id, START, linked_timer_policy=LinkedTimerPolicy.DELETE
        )
        session.commit()

        assert _stored(test_engine, timer.id) is None
        assert [item["message"]["type"] for item in after_commit_items] == ["timer.deleted"]


# ============================================================
# Todo 쪽 흐름이 투영 일정을 지울 때 — 묻지 않고 일정 연결만 해제
# ============================================================

class TestProjectionDeletedByTodo:
    def _todo_with_projection(self, session, group_id) -> tuple[Todo, UUID]:
        todo = _todo(session, group_id, deadline=START)
        [projection] = schedule_crud.get_schedules_by_source_todo_id(session, todo.id, OWNER.sub)
        return todo, projection.id

    def _schedule_only_timer(self, session, schedule_id) -> TimerSession:
        timer = _timer(session, schedule_id=schedule_id)  # 투영의 Todo가 함께 연결된다
        TimerService(session, OWNER).update_timer(timer.id, TimerUpdate(todo_id=None))
        session.commit()
        return timer

    def test_deadline_removal_unlinks_schedule_and_keeps_todo(
            self, session, test_engine, group_id, after_commit_items):
        todo, projection_id = self._todo_with_projection(session, group_id)
        timer = _timer(session, todo_id=todo.id)
        assert timer.schedule_id == projection_id
        after_commit_items.clear()

        TodoService(session, OWNER).update_todo(
            todo.id, TodoUpdate(deadline=None, linked_schedule_policy=LinkedSchedulePolicy.DELETE)
        )
        session.commit()

        stored = _stored(test_engine, timer.id)
        assert stored.schedule_id is None
        assert stored.todo_id == todo.id
        [item] = after_commit_items
        assert item["message"]["type"] == "timer.updated"
        assert item["message"]["payload"]["timer"]["schedule_id"] is None
        assert item["message"]["payload"]["timer"]["todo_id"] == str(todo.id)

    def test_todo_delete_unlinks_schedule_only_timer_without_policy(
            self, session, test_engine, group_id, after_commit_items):
        todo, projection_id = self._todo_with_projection(session, group_id)
        timer = self._schedule_only_timer(session, projection_id)
        after_commit_items.clear()

        TodoService(session, OWNER).delete_todo(todo.id, LinkedSchedulePolicy.DELETE)
        session.commit()

        assert _stored(test_engine, timer.id).schedule_id is None
        [item] = after_commit_items
        assert item["message"]["type"] == "timer.updated"
        assert item["message"]["payload"]["timer"]["schedule_id"] is None

    @pytest.mark.parametrize("policy, todo_timer_event", [
        (LinkedTimerPolicy.UNLINK, "timer.updated"),
        (LinkedTimerPolicy.DELETE, "timer.deleted"),
    ])
    def test_todo_policy_governs_timers_linked_to_both(
            self, session, test_engine, group_id, after_commit_items, policy, todo_timer_event):
        """Todo에도 연결된 타이머는 Todo의 정책만 따르고 타이머마다 이벤트는 하나"""
        todo, projection_id = self._todo_with_projection(session, group_id)
        both = _timer(session, todo_id=todo.id)
        schedule_only = self._schedule_only_timer(session, projection_id)
        after_commit_items.clear()

        TodoService(session, OWNER).delete_todo(todo.id, LinkedSchedulePolicy.DELETE, policy)
        session.commit()

        events = {}
        for item in after_commit_items:
            payload = item["message"]["payload"]
            timer_id = payload["timer"]["id"] if payload["timer"] else payload["timer_id"]
            assert timer_id not in events
            events[timer_id] = item["message"]
        assert {timer_id: m["type"] for timer_id, m in events.items()} == {
            str(both.id): todo_timer_event,
            str(schedule_only.id): "timer.updated",
        }
        if policy == LinkedTimerPolicy.UNLINK:
            stored = _stored(test_engine, both.id)
            assert (stored.todo_id, stored.schedule_id) == (None, None)
            assert events[str(both.id)]["payload"]["timer"]["schedule_id"] is None
        else:
            assert _stored(test_engine, both.id) is None
        assert _stored(test_engine, schedule_only.id).schedule_id is None
