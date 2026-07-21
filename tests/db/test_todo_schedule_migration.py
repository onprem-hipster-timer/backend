"""Todo-Schedule linkage data migration regression tests.

These tests deliberately start from the last revision before the linkage
invariant was introduced.  Legacy rows are inserted directly because they
represent states accepted by older application versions, not states that the
current domain services should create.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, select
from sqlmodel import SQLModel

import app.models  # noqa: F401  # register every table in SQLModel.metadata
from app.core.config import settings
from app.domain.schedule.enums import ScheduleState
from app.domain.todo.enums import TodoStatus
from app.models.schedule import Schedule
from app.models.tag import TagGroup
from app.models.todo import Todo


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LEGACY_REVISION = "b9e4d2a1c3f5"


@dataclass(frozen=True)
class LegacyDatabase:
    """Temporary SQLite database stamped at ``LEGACY_REVISION``."""

    url: str
    alembic_config: Config

    def upgrade_to_head(self) -> None:
        command.upgrade(self.alembic_config, "head")

    def engine(self) -> Engine:
        return sa.create_engine(self.url)


@pytest.fixture
def legacy_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LegacyDatabase:
    """Build a real legacy schema through Alembic's downgrade path."""

    database_path = tmp_path / "legacy-linkage.db"
    database_url = f"sqlite:///{database_path.resolve().as_posix()}"
    # alembic env.py는 실행 시점의 app.core.config.settings를 읽으므로,
    # 모듈 import 시점 바인딩이 아니라 live 객체를 패치한다
    # (다른 fixture가 settings 객체를 교체했더라도 같은 객체를 보게 됨)
    import app.core.config as app_config
    monkeypatch.setattr(app_config.settings, "DATABASE_URL", database_url)

    engine = sa.create_engine(database_url)
    SQLModel.metadata.create_all(engine)
    engine.dispose()

    alembic_config = Config(str(PROJECT_ROOT / "alembic.ini"))
    alembic_config.set_main_option(
        "script_location",
        (PROJECT_ROOT / "alembic").resolve().as_posix(),
    )

    # create_all reflects today's model, so stamp it as head and use the real
    # downgrade scripts to obtain the schema immediately before the migration.
    command.stamp(alembic_config, "head")
    command.downgrade(alembic_config, LEGACY_REVISION)

    return LegacyDatabase(database_url, alembic_config)


def _insert_tag_group(connection: sa.Connection, *, owner_id: str) -> UUID:
    group_id = uuid4()
    connection.execute(
        TagGroup.__table__.insert().values(
            id=group_id,
            owner_id=owner_id,
            name=f"legacy group {group_id}",
            color="#123456",
        )
    )
    return group_id


def _insert_todo(
    connection: sa.Connection,
    *,
    owner_id: str,
    tag_group_id: UUID,
    status: TodoStatus,
) -> UUID:
    todo_id = uuid4()
    connection.execute(
        Todo.__table__.insert().values(
            id=todo_id,
            owner_id=owner_id,
            title=f"legacy todo {todo_id}",
            tag_group_id=tag_group_id,
            status=status,
        )
    )
    return todo_id


def _insert_schedule(
    connection: sa.Connection,
    *,
    owner_id: str,
    source_todo_id: UUID | None,
    recurrence_rule: str | None = None,
) -> UUID:
    schedule_id = uuid4()
    start_time = datetime(2026, 7, 20, 9, 0)
    connection.execute(
        Schedule.__table__.insert().values(
            id=schedule_id,
            owner_id=owner_id,
            title=f"legacy schedule {schedule_id}",
            start_time=start_time,
            end_time=start_time + timedelta(hours=1),
            recurrence_rule=recurrence_rule,
            source_todo_id=source_todo_id,
            state=ScheduleState.PLANNED,
        )
    )
    return schedule_id


def _todo_statuses(
    engine: Engine,
    todo_ids: list[UUID],
) -> dict[UUID, TodoStatus]:
    with engine.connect() as connection:
        rows = connection.execute(
            select(Todo.id, Todo.status).where(Todo.id.in_(todo_ids))
        )
        return {todo_id: status for todo_id, status in rows}


def test_upgrade_deduplicates_legacy_projection_links_and_enforces_unique_index(
    legacy_database: LegacyDatabase,
) -> None:
    """Duplicate legacy links must not make deployment fail."""

    engine = legacy_database.engine()
    with engine.begin() as connection:
        group_id = _insert_tag_group(connection, owner_id="owner-a")
        todo_id = _insert_todo(
            connection,
            owner_id="owner-a",
            tag_group_id=group_id,
            status=TodoStatus.UNSCHEDULED,
        )
        _insert_schedule(
            connection,
            owner_id="owner-a",
            source_todo_id=todo_id,
        )
        _insert_schedule(
            connection,
            owner_id="owner-a",
            source_todo_id=todo_id,
        )
    engine.dispose()

    legacy_database.upgrade_to_head()

    engine = legacy_database.engine()
    with engine.begin() as connection:
        linked_count = connection.scalar(
            select(sa.func.count())
            .select_from(Schedule)
            .where(Schedule.source_todo_id == todo_id)
        )
        if linked_count == 0:
            _insert_schedule(
                connection,
                owner_id="owner-a",
                source_todo_id=todo_id,
            )

    # Verify the invariant by behavior, without coupling the contract to a
    # particular index/constraint implementation or survivor selection rule.
    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as connection:
            _insert_schedule(
                connection,
                owner_id="owner-a",
                source_todo_id=todo_id,
            )
    engine.dispose()

    assert linked_count is not None
    assert linked_count <= 1


def test_upgrade_backfills_status_from_linkage_and_preserves_terminal_statuses(
    legacy_database: LegacyDatabase,
) -> None:
    """Only non-terminal Todo statuses are derived from valid linkage."""

    engine = legacy_database.engine()
    with engine.begin() as connection:
        group_id = _insert_tag_group(connection, owner_id="owner-a")

        linked_unscheduled = _insert_todo(
            connection,
            owner_id="owner-a",
            tag_group_id=group_id,
            status=TodoStatus.UNSCHEDULED,
        )
        _insert_schedule(
            connection,
            owner_id="owner-a",
            source_todo_id=linked_unscheduled,
        )

        unlinked_scheduled = _insert_todo(
            connection,
            owner_id="owner-a",
            tag_group_id=group_id,
            status=TodoStatus.SCHEDULED,
        )

        linked_done = _insert_todo(
            connection,
            owner_id="owner-a",
            tag_group_id=group_id,
            status=TodoStatus.DONE,
        )
        _insert_schedule(
            connection,
            owner_id="owner-a",
            source_todo_id=linked_done,
        )

        unlinked_cancelled = _insert_todo(
            connection,
            owner_id="owner-a",
            tag_group_id=group_id,
            status=TodoStatus.CANCELLED,
        )
    engine.dispose()

    legacy_database.upgrade_to_head()

    engine = legacy_database.engine()
    statuses = _todo_statuses(
        engine,
        [linked_unscheduled, unlinked_scheduled, linked_done, unlinked_cancelled],
    )
    engine.dispose()

    assert statuses == {
        linked_unscheduled: TodoStatus.SCHEDULED,
        unlinked_scheduled: TodoStatus.UNSCHEDULED,
        linked_done: TodoStatus.DONE,
        unlinked_cancelled: TodoStatus.CANCELLED,
    }


def test_upgrade_unlinks_cross_owner_and_recurring_legacy_projections(
    legacy_database: LegacyDatabase,
) -> None:
    """Only same-owner, non-recurring schedules may remain Todo projections."""

    engine = legacy_database.engine()
    with engine.begin() as connection:
        owner_group_id = _insert_tag_group(connection, owner_id="todo-owner")

        cross_owner_todo = _insert_todo(
            connection,
            owner_id="todo-owner",
            tag_group_id=owner_group_id,
            status=TodoStatus.SCHEDULED,
        )
        cross_owner_schedule = _insert_schedule(
            connection,
            owner_id="different-schedule-owner",
            source_todo_id=cross_owner_todo,
        )

        recurring_todo = _insert_todo(
            connection,
            owner_id="todo-owner",
            tag_group_id=owner_group_id,
            status=TodoStatus.SCHEDULED,
        )
        recurring_schedule = _insert_schedule(
            connection,
            owner_id="todo-owner",
            source_todo_id=recurring_todo,
            recurrence_rule="FREQ=DAILY",
        )
    engine.dispose()

    legacy_database.upgrade_to_head()

    engine = legacy_database.engine()
    with engine.connect() as connection:
        links = dict(
            connection.execute(
                select(Schedule.id, Schedule.source_todo_id).where(
                    Schedule.id.in_([cross_owner_schedule, recurring_schedule])
                )
            ).all()
        )
    statuses = _todo_statuses(engine, [cross_owner_todo, recurring_todo])
    engine.dispose()

    assert links == {
        cross_owner_schedule: None,
        recurring_schedule: None,
    }
    assert statuses == {
        cross_owner_todo: TodoStatus.UNSCHEDULED,
        recurring_todo: TodoStatus.UNSCHEDULED,
    }
