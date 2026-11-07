"""
타이머 완료·취소와 연결 Todo 상태 테스트

- 타이머 완료 → 연결 Todo DONE, 취소 → CANCELLED (app/domain/todo/event_handlers.py)
- Todo가 DONE·CANCELLED가 되면 실행 중·일시정지 타이머를 완료·취소, UNSCHEDULED·SCHEDULED가
  되면 타이머는 그대로 두고 update 이벤트만 (app/domain/timer/event_handlers.py)
- 이미 DONE·CANCELLED인 Todo는 그대로 둔다 — 그래서 양방향 전파가 한 번에 끝난다
실시간 이벤트는 커밋된 뒤에만 sink로 넘어가므로 실제로 커밋하는 세션을 쓴다.
"""
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import update
from sqlmodel import Session

from app.crud import schedule as schedule_crud
from app.domain.schedule.enums import SourceTodoPolicy
from app.domain.schedule.service import ScheduleService
from app.domain.tag.schema.dto import TagGroupCreate
from app.domain.tag.service import TagService
from app.domain.timer.events import TimerCancelled, TimerCompleted
from app.domain.timer.model import TimerSession
from app.domain.timer.schema.dto import TimerCreate, TimerUpdate
from app.domain.timer.service import TimerService
from app.domain.todo.enums import LinkedSchedulePolicy, TodoStatus
from app.domain.todo.events import TodoStatusChanged
from app.domain.todo.model import Todo
from app.domain.todo.schema.dto import TodoCreate, TodoUpdate
from app.domain.todo.service import TodoService
from app.domain.user.service import UserProfileService
from app.shared.events import EventOrigin
from app.shared.messagebus import HANDLERS
from tests.conftest import make_user

OWNER = make_user("owner", name="Owner Name")
DEADLINE = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def session(test_engine):
    with Session(test_engine) as session:
        # 실시간 이벤트의 actor_name은 프로필 캐시(요청마다 JWT name으로 동기화)에서 온다
        UserProfileService(session, OWNER).sync_from_current_user()
        session.commit()
        yield session


@pytest.fixture
def handled(monkeypatch) -> list:
    """dispatch된 TodoStatusChanged·TimerCompleted·TimerCancelled를 순서대로 기록"""
    events = []
    for event_type in (TodoStatusChanged, TimerCompleted, TimerCancelled):
        monkeypatch.setitem(HANDLERS, event_type, [*HANDLERS.get(event_type, []), lambda e, _: events.append(e)])
    return events


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
    timer = TimerService(session, OWNER).create_timer(TimerCreate(allocated_duration=1500, **links))
    session.commit()
    return timer


def _stored_status(test_engine, model, resource_id: UUID) -> str:
    with Session(test_engine) as fresh:
        return fresh.get(model, resource_id).status


def _stored_timer(test_engine, timer_id: UUID) -> TimerSession:
    with Session(test_engine) as fresh:
        return fresh.get(TimerSession, timer_id)


def _set_status(session, todo_id: UUID, status: TodoStatus) -> None:
    TodoService(session, OWNER).update_todo(todo_id, TodoUpdate(status=status))
    session.commit()


def _assert_nudged(test_engine, timer: TimerSession, before: datetime, after_commit_items: list) -> None:
    """타이머는 실행 중 그대로, updated_at만 갱신되고 timer.updated(update)가 하나 나갔다"""
    stored = _stored_timer(test_engine, timer.id)
    assert stored.status == "RUNNING"
    assert stored.updated_at > before
    [item] = after_commit_items
    message = item["message"]
    assert (message["type"], message["payload"]["action"]) == ("timer.updated", "update")
    assert message["payload"]["timer"]["id"] == str(timer.id)
    assert message["payload"]["timer"]["status"] == "RUNNING"


# ============================================================
# 타이머 → Todo
# ============================================================

class TestTimerFinishesTodo:
    @pytest.mark.parametrize("deadline, before", [
        (None, TodoStatus.UNSCHEDULED),
        (DEADLINE, TodoStatus.SCHEDULED),
    ])
    def test_stop_completes_todo(self, session, test_engine, group_id, deadline, before):
        todo = _todo(session, group_id, deadline=deadline)
        assert todo.status == before
        timer = _timer(session, todo_id=todo.id)

        TimerService(session, OWNER).stop_timer(timer.id)
        session.commit()

        assert _stored_status(test_engine, TimerSession, timer.id) == "COMPLETED"
        assert _stored_status(test_engine, Todo, todo.id) == TodoStatus.DONE

    def test_stop_keeps_cancelled_todo(self, session, test_engine, group_id):
        todo = _todo(session, group_id, status=TodoStatus.CANCELLED)
        timer = _timer(session, todo_id=todo.id)

        TimerService(session, OWNER).stop_timer(timer.id)
        session.commit()

        assert _stored_status(test_engine, Todo, todo.id) == TodoStatus.CANCELLED

    def test_stop_without_todo_changes_no_todo(self, session, test_engine, group_id):
        todo = _todo(session, group_id)
        timer = _timer(session)

        TimerService(session, OWNER).stop_timer(timer.id)
        session.commit()

        assert _stored_status(test_engine, TimerSession, timer.id) == "COMPLETED"
        assert _stored_status(test_engine, Todo, todo.id) == TodoStatus.UNSCHEDULED

    def test_cancel_cancels_todo(self, session, test_engine, group_id):
        todo = _todo(session, group_id)
        timer = _timer(session, todo_id=todo.id)

        TimerService(session, OWNER).cancel_timer(timer.id)
        session.commit()

        assert _stored_status(test_engine, TimerSession, timer.id) == "CANCELLED"
        assert _stored_status(test_engine, Todo, todo.id) == TodoStatus.CANCELLED

    def test_stop_completes_other_active_timer_of_todo(
            self, session, test_engine, group_id, after_commit_items, handled):
        """타이머 완료로 Todo가 DONE이 되면 같은 Todo의 다른 실행 중 타이머도 완료된다"""
        todo = _todo(session, group_id)
        stopped = _timer(session, todo_id=todo.id)
        other = _timer(session, todo_id=todo.id)
        after_commit_items.clear()

        TimerService(session, OWNER).stop_timer(stopped.id)
        session.commit()

        assert _stored_status(test_engine, TimerSession, other.id) == "COMPLETED"
        assert [(type(e), getattr(e, "timer_id", None)) for e in handled] == [
            (TimerCompleted, stopped.id),
            (TodoStatusChanged, None),
            (TimerCompleted, other.id),
        ]
        assert handled[1].origin == EventOrigin.TIMER
        assert [(i["message"]["payload"]["timer"]["id"], i["message"]["payload"]["action"])
                for i in after_commit_items] == [(str(stopped.id), "stop"), (str(other.id), "stop")]

    def test_cancel_keeps_done_todo(self, session, test_engine, group_id):
        todo = _todo(session, group_id, status=TodoStatus.DONE)
        timer = _timer(session, todo_id=todo.id)

        TimerService(session, OWNER).cancel_timer(timer.id)
        session.commit()

        assert _stored_status(test_engine, Todo, todo.id) == TodoStatus.DONE


# ============================================================
# Todo → 타이머
# ============================================================

class TestTodoFinishesTimers:
    def test_done_completes_running_timer_with_running_segment(
            self, session, test_engine, group_id, after_commit_items):
        todo = _todo(session, group_id)
        timer = _timer(session, todo_id=todo.id)
        session.execute(
            update(TimerSession)
            .where(TimerSession.id == timer.id)
            .values(started_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=120))
        )
        session.commit()
        after_commit_items.clear()

        _set_status(session, todo.id, TodoStatus.DONE)

        stored = _stored_timer(test_engine, timer.id)
        assert stored.status == "COMPLETED"
        assert stored.elapsed_time >= 120
        assert stored.ended_at is not None
        assert stored.pause_history[-1]["action"] == "stop"
        [item] = after_commit_items
        assert item["users"] == {OWNER.sub}
        message = item["message"]
        assert message["type"] == "timer.updated"
        assert message["payload"]["action"] == "stop"
        assert message["payload"]["actor_name"] == "Owner Name"
        assert message["payload"]["timer"]["status"] == "COMPLETED"
        assert message["payload"]["timer"]["elapsed_time"] == stored.elapsed_time

    def test_done_completes_paused_timer(self, session, test_engine, group_id):
        todo = _todo(session, group_id)
        timer = _timer(session, todo_id=todo.id)
        paused = TimerService(session, OWNER).pause_timer(timer.id)
        paused_elapsed = paused.elapsed_time
        session.commit()

        _set_status(session, todo.id, TodoStatus.DONE)

        stored = _stored_timer(test_engine, timer.id)
        assert stored.status == "COMPLETED"
        assert stored.elapsed_time == paused_elapsed

    def test_cancelled_cancels_timer(self, session, test_engine, group_id, after_commit_items):
        todo = _todo(session, group_id)
        timer = _timer(session, todo_id=todo.id)
        after_commit_items.clear()

        _set_status(session, todo.id, TodoStatus.CANCELLED)

        assert _stored_status(test_engine, TimerSession, timer.id) == "CANCELLED"
        [item] = after_commit_items
        assert item["message"]["type"] == "timer.updated"
        assert item["message"]["payload"]["action"] == "cancel"
        assert item["message"]["payload"]["timer"]["status"] == "CANCELLED"

    @pytest.mark.parametrize("deadline, reopened", [
        (None, TodoStatus.UNSCHEDULED),
        (DEADLINE, TodoStatus.SCHEDULED),
    ])
    def test_reopen_keeps_timer_running_and_sends_update(
            self, session, test_engine, group_id, after_commit_items, handled, deadline, reopened):
        todo = _todo(session, group_id, deadline=deadline, status=TodoStatus.DONE)
        timer = _timer(session, todo_id=todo.id)
        before = timer.updated_at
        after_commit_items.clear()

        _set_status(session, todo.id, reopened)

        assert _stored_status(test_engine, Todo, todo.id) == reopened
        _assert_nudged(test_engine, timer, before, after_commit_items)
        assert [(type(e), e.status) for e in handled] == [(TodoStatusChanged, reopened)]

    @pytest.mark.parametrize("update, flipped", [
        (TodoUpdate(deadline=DEADLINE), TodoStatus.SCHEDULED),
        (TodoUpdate(deadline=None, linked_schedule_policy=LinkedSchedulePolicy.UNLINK), TodoStatus.UNSCHEDULED),
    ])
    def test_deadline_flip_sends_update_once(
            self, session, test_engine, group_id, after_commit_items, handled, update, flipped):
        todo = _todo(session, group_id, deadline=None if flipped == TodoStatus.SCHEDULED else DEADLINE)
        timer = _timer(session, todo_id=todo.id)
        before = timer.updated_at
        after_commit_items.clear()

        TodoService(session, OWNER).update_todo(todo.id, update)
        session.commit()

        assert _stored_status(test_engine, Todo, todo.id) == flipped
        _assert_nudged(test_engine, timer, before, after_commit_items)
        assert [(type(e), e.status) for e in handled] == [(TodoStatusChanged, flipped)]

    def test_projection_deleted_from_schedule_side_sends_update_once(
            self, session, test_engine, group_id, after_commit_items, handled):
        todo = _todo(session, group_id, deadline=DEADLINE)
        timer = _timer(session, todo_id=todo.id)
        TimerService(session, OWNER).update_timer(timer.id, TimerUpdate(schedule_id=None))
        session.commit()
        before = _stored_timer(test_engine, timer.id).updated_at
        [projection] = schedule_crud.get_schedules_by_source_todo_id(session, todo.id, OWNER.sub)
        after_commit_items.clear()

        ScheduleService(session, OWNER).delete_schedule(projection.id, SourceTodoPolicy.KEEP_DEADLINE)
        session.commit()

        assert _stored_status(test_engine, Todo, todo.id) == TodoStatus.UNSCHEDULED
        _assert_nudged(test_engine, timer, before, after_commit_items)
        assert [(type(e), e.status, e.origin) for e in handled] == [
            (TodoStatusChanged, TodoStatus.UNSCHEDULED, EventOrigin.SCHEDULE)
        ]

    def test_done_again_collects_nothing(self, session, test_engine, group_id, after_commit_items, handled):
        todo = _todo(session, group_id, status=TodoStatus.DONE)
        timer = _timer(session, todo_id=todo.id)
        after_commit_items.clear()

        _set_status(session, todo.id, TodoStatus.DONE)

        assert _stored_status(test_engine, TimerSession, timer.id) == "RUNNING"
        assert after_commit_items == []
        assert handled == []

    def test_propagation_stops_after_one_round_trip(self, session, test_engine, group_id, handled):
        """Todo DONE → 타이머 완료 → TimerCompleted는 Todo가 이미 DONE이라 더 퍼지지 않는다"""
        todo = _todo(session, group_id)
        timer = _timer(session, todo_id=todo.id)

        _set_status(session, todo.id, TodoStatus.DONE)

        assert [type(event) for event in handled] == [TodoStatusChanged, TimerCompleted]
        assert handled[1].timer_id == timer.id
        assert _stored_status(test_engine, Todo, todo.id) == TodoStatus.DONE
