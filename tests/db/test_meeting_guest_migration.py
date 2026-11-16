"""미팅의 게스트 마이그레이션

alembic/versions/2026_11_17_1000-a4c8e2f6b1d3_add_allow_guests_to_meeting.py
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlmodel import SQLModel

import app.models  # noqa: F401  # register every table in SQLModel.metadata
import app.models.holiday  # noqa: F401
from tests.db.conftest import database_url_for, migration_database

BEFORE_ALLOW_GUESTS = "b3e7c1d9f4a2"
ALLOW_GUESTS = "a4c8e2f6b1d3"

_INSERT_MEETING = sa.text(
    "INSERT INTO meeting (id, owner_id, title, start_date, end_date, timezone, available_days,"
    " start_time, end_time, time_slot_minutes, created_at, updated_at)"
    " VALUES (:id, 'owner', 'm', '2024-02-05', '2024-02-09', 'UTC', '[0]', '09:00:00', '18:00:00', 30,"
    " '2026-11-17 00:00:00', '2026-11-17 00:00:00')"
)


@pytest.fixture(params=["sqlite", "postgresql"])
def database_url(request, tmp_path: Path) -> str:
    return database_url_for(request.param, tmp_path / "meeting_guest.db")


@pytest.fixture
def engine_and_config(database_url: str, monkeypatch: pytest.MonkeyPatch):
    with migration_database(monkeypatch, database_url) as engine_and_config:
        yield engine_and_config


def _columns(engine: sa.Engine, table: str) -> dict[str, dict]:
    return {c["name"]: c for c in sa.inspect(engine).get_columns(table)}


def _single_head(engine: sa.Engine, config) -> None:
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    heads = ScriptDirectory.from_config(config).get_heads()
    assert len(heads) == 1
    assert current == heads[0]


def test_existing_meetings_get_false_and_downgrade_drops_column(engine_and_config) -> None:
    engine, config = engine_and_config
    command.stamp(config, "head")
    command.downgrade(config, BEFORE_ALLOW_GUESTS)
    assert "allow_guests" not in _columns(engine, "meeting")
    with engine.begin() as connection:
        connection.execute(_INSERT_MEETING, {"id": "a" * 32})

    command.upgrade(config, ALLOW_GUESTS)

    assert _columns(engine, "meeting")["allow_guests"]["nullable"] is False
    with engine.connect() as connection:
        assert connection.execute(sa.text("SELECT allow_guests FROM meeting")).scalar_one() in (False, 0)

    command.downgrade(config, BEFORE_ALLOW_GUESTS)
    assert "allow_guests" not in _columns(engine, "meeting")
    with engine.connect() as connection:
        assert connection.execute(sa.text("SELECT title FROM meeting")).scalar_one() == "m"

    command.upgrade(config, "head")
    _single_head(engine, config)


def test_upgrade_skips_column_that_create_all_already_made(engine_and_config) -> None:
    engine, config = engine_and_config
    command.stamp(config, BEFORE_ALLOW_GUESTS)

    command.upgrade(config, "head")

    assert _columns(engine, "meeting")["allow_guests"]["nullable"] is False


def test_migrated_meeting_columns_match_model(engine_and_config, tmp_path: Path) -> None:
    migrated, config = engine_and_config
    command.stamp(config, "head")
    command.downgrade(config, BEFORE_ALLOW_GUESTS)
    command.upgrade(config, "head")
    modeled = sa.create_engine(f"sqlite:///{(tmp_path / 'modeled.db').resolve().as_posix()}")
    SQLModel.metadata.create_all(modeled)

    def shape(engine: sa.Engine) -> dict[str, bool]:
        return {name: c["nullable"] for name, c in _columns(engine, "meeting").items()}

    assert shape(migrated) == shape(modeled)
    if migrated.dialect.name == "sqlite":
        assert _columns(migrated, "meeting")["allow_guests"]["default"] == _columns(modeled, "meeting")["allow_guests"]["default"]
    modeled.dispose()
