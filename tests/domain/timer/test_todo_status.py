"""
타이머 완료·취소와 연결 Todo 상태 테스트

- 타이머 완료 → 연결 Todo DONE, 취소 → CANCELLED (app/domain/todo/event_handlers.py)
- 이미 DONE·CANCELLED인 Todo는 그대로 둔다
"""
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlmodel import Session

from app.domain.tag.schema.dto import TagGroupCreate
from app.domain.tag.service import TagService
from app.domain.timer.model import TimerSession
from app.domain.timer.schema.dto import TimerCreate
from app.domain.timer.service import TimerService
from app.domain.todo.enums import TodoStatus
from app.domain.todo.model import Todo
from app.domain.todo.schema.dto import TodoCreate
from app.domain.todo.service import TodoService
from tests.conftest import make_user

OWNER = make_user("owner", name="Owner Name")
DEADLINE = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def session(test_engine):
    with Session(test_engine) as session:
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
    timer = TimerService(session, OWNER).create_timer(TimerCreate(allocated_duration=1500, **links))
    session.commit()
    return timer


def _stored_status(test_engine, model, resource_id: UUID) -> str:
    with Session(test_engine) as fresh:
        return fresh.get(model, resource_id).status


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

    def test_cancel_keeps_done_todo(self, session, test_engine, group_id):
        todo = _todo(session, group_id, status=TodoStatus.DONE)
        timer = _timer(session, todo_id=todo.id)

        TimerService(session, OWNER).cancel_timer(timer.id)
        session.commit()

        assert _stored_status(test_engine, Todo, todo.id) == TodoStatus.DONE
