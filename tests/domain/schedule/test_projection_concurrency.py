"""PostgreSQL concurrency contracts for the Todo/Schedule projection pair.

SQLite serializes writes differently and cannot reproduce PostgreSQL row-lock
deadlocks, so this module is intentionally opt-in through TEST_DATABASE_URL.
The SQL hooks only coordinate the first relevant write in each worker.  Their
barriers time out harmlessly when a fixed implementation serializes both paths
using one canonical lock order.
"""

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest
from sqlalchemy import event, text
from sqlmodel import Session, select

from app.domain.schedule.schema.dto import ScheduleCreate, ScheduleUpdate
from app.domain.schedule.service import ScheduleService
from app.domain.tag.schema.dto import TagGroupCreate
from app.domain.tag.service import TagService
from app.domain.todo.enums import TodoStatus
from app.domain.todo.schema.dto import TodoCreate, TodoUpdate
from app.domain.todo.service import TodoService
from app.models.schedule import Schedule
from app.models.todo import Todo
from app.shared.uow import clear_events


_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
_IS_POSTGRESQL = _DATABASE_URL.startswith("postgresql")
_GATE_TIMEOUT_SECONDS = 3
_START_GATE_TIMEOUT_SECONDS = 10
_FUTURE_TIMEOUT_SECONDS = 20

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _IS_POSTGRESQL,
        reason="requires PostgreSQL via TEST_DATABASE_URL for row-lock semantics",
    ),
]


def _set_bounded_postgresql_waits(session: Session) -> None:
    """Keep a regression failure bounded even if PostgreSQL cannot resolve it."""
    session.exec(text("SET LOCAL lock_timeout = '8s'"))
    session.exec(text("SET LOCAL statement_timeout = '12s'"))


def _normalize_sql(statement: str) -> str:
    return " ".join(statement.lower().replace('"', "").split())


def _install_write_gate(engine, thread_state, expected_write_by_role):
    """Return an engine listener that aligns two independently locked writes."""
    gate = threading.Barrier(2)
    seen_roles: set[str] = set()
    seen_lock = threading.Lock()

    def after_cursor_execute(
        conn, cursor, statement, parameters, context, executemany
    ) -> None:
        role = getattr(thread_state, "role", None)
        expected_prefix = expected_write_by_role.get(role)
        if expected_prefix is None:
            return
        if not _normalize_sql(statement).startswith(expected_prefix):
            return

        with seen_lock:
            if role in seen_roles:
                return
            seen_roles.add(role)

        try:
            gate.wait(timeout=_GATE_TIMEOUT_SECONDS)
        except threading.BrokenBarrierError:
            # With a canonical lock order, one transaction may be blocked before
            # its role-specific write. Let the first transaction finish so the
            # second can continue and prove that both operations complete.
            pass

    event.listen(engine, "after_cursor_execute", after_cursor_execute)
    return after_cursor_execute


def _run_two_workers(worker, roles):
    start_gate = threading.Barrier(2)
    executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="projection-race")
    futures = [executor.submit(worker, role, start_gate) for role in roles]
    try:
        return [future.result(timeout=_FUTURE_TIMEOUT_SECONDS) for future in futures]
    finally:
        executor.shutdown(wait=True, cancel_futures=True)


def _seed_tag_group_and_schedule(test_engine, test_user):
    start = datetime(2030, 1, 1, 10, 0)
    with Session(test_engine) as session:
        group = TagService(session, test_user).create_tag_group(
            TagGroupCreate(
                name="Projection concurrency",
                color="#224488",
            )
        )
        schedule = ScheduleService(session, test_user).create_schedule(
            ScheduleCreate(
                title="Unlinked schedule",
                start_time=start,
                end_time=start + timedelta(hours=1),
            )
        )
        session.commit()
        return group.id, schedule.id


def _seed_linked_projection(test_engine, test_user):
    deadline = datetime(2030, 2, 1, 10, 0)
    with Session(test_engine) as session:
        group = TagService(session, test_user).create_tag_group(
            TagGroupCreate(
                name="Projection lock order",
                color="#662288",
            )
        )
        todo = TodoService(session, test_user).create_todo(
            TodoCreate(
                title="Linked Todo",
                tag_group_id=group.id,
                deadline=deadline,
            )
        )
        projection = session.exec(
            select(Schedule).where(Schedule.source_todo_id == todo.id)
        ).one()
        session.commit()
        return todo.id, projection.id, deadline


def test_concurrent_create_todo_from_one_schedule_has_one_winner_and_no_orphan(
    test_engine,
    test_user,
):
    group_id, schedule_id = _seed_tag_group_and_schedule(test_engine, test_user)
    thread_state = threading.local()
    listener = _install_write_gate(
        test_engine,
        thread_state,
        {
            "creator-1": "insert into todo ",
            "creator-2": "insert into todo ",
        },
    )

    def worker(role, start_gate):
        thread_state.role = role
        with Session(test_engine) as session:
            try:
                _set_bounded_postgresql_waits(session)
                start_gate.wait(timeout=_START_GATE_TIMEOUT_SECONDS)
                todo = ScheduleService(session, test_user).create_todo_from_schedule(
                    schedule_id,
                    group_id,
                )
                todo_id = todo.id
                session.commit()
                return {"outcome": "success", "todo_id": todo_id}
            except Exception as exc:
                session.rollback()
                clear_events(session)
                return {
                    "outcome": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                }

    try:
        results = _run_two_workers(worker, ("creator-1", "creator-2"))
    finally:
        event.remove(test_engine, "after_cursor_execute", listener)

    successes = [result for result in results if result["outcome"] == "success"]
    with Session(test_engine) as session:
        schedule = session.get(Schedule, schedule_id)
        todos = list(
            session.exec(
                select(Todo).where(Todo.owner_id == test_user.sub)
            ).all()
        )
        orphan_ids = [
            todo.id
            for todo in todos
            if todo.status == TodoStatus.SCHEDULED
            and todo.id != schedule.source_todo_id
        ]

    assert (len(successes), orphan_ids) == (1, []), results


def test_concurrent_todo_and_schedule_time_updates_complete_without_deadlock(
    test_engine,
    test_user,
):
    todo_id, schedule_id, original_deadline = _seed_linked_projection(
        test_engine,
        test_user,
    )
    thread_state = threading.local()
    listener = _install_write_gate(
        test_engine,
        thread_state,
        {
            "todo": "update todo ",
            "schedule": "update schedule ",
        },
    )

    todo_deadline = original_deadline + timedelta(minutes=10)
    schedule_start = original_deadline + timedelta(minutes=20)

    def worker(role, start_gate):
        thread_state.role = role
        with Session(test_engine) as session:
            try:
                _set_bounded_postgresql_waits(session)
                start_gate.wait(timeout=_START_GATE_TIMEOUT_SECONDS)
                if role == "todo":
                    TodoService(session, test_user).update_todo(
                        todo_id,
                        TodoUpdate(deadline=todo_deadline),
                    )
                else:
                    ScheduleService(session, test_user).update_schedule(
                        schedule_id,
                        ScheduleUpdate(start_time=schedule_start),
                    )
                session.commit()
                return {"outcome": "success", "role": role}
            except Exception as exc:
                session.rollback()
                clear_events(session)
                return {
                    "outcome": "error",
                    "role": role,
                    "error": f"{type(exc).__name__}: {exc}",
                }

    try:
        results = _run_two_workers(worker, ("todo", "schedule"))
    finally:
        event.remove(test_engine, "after_cursor_execute", listener)

    with Session(test_engine) as session:
        todo = session.get(Todo, todo_id)
        schedule = session.get(Schedule, schedule_id)
        projection_is_consistent = todo.deadline == schedule.start_time

    assert [result["outcome"] for result in results] == ["success", "success"], results
    assert projection_is_consistent
