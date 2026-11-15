"""meeting에 시간대를 더하는 마이그레이션

alembic/versions/2026_11_14_1000-f3a39109a3ef_add_timezone_to_meeting.py
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from sqlmodel import SQLModel

import app.models  # noqa: F401  # register every table in SQLModel.metadata
import app.models.holiday  # noqa: F401
from tests.db.conftest import database_url_for, migration_database

BEFORE_TIMEZONE = "3f1fcd3dae5f"


@pytest.fixture(params=["sqlite", "postgresql"])
def database_url(request, tmp_path: Path) -> str:
    return database_url_for(request.param, tmp_path / "meeting_tz.db")


@pytest.fixture
def engine_and_config(database_url: str, monkeypatch: pytest.MonkeyPatch):
    with migration_database(monkeypatch, database_url) as engine_and_config:
        yield engine_and_config


def _columns(engine: sa.Engine) -> dict[str, dict]:
    return {c["name"]: c for c in sa.inspect(engine).get_columns("meeting")}


def test_existing_meetings_get_utc_and_downgrade_drops_column(engine_and_config) -> None:
    engine, config = engine_and_config
    command.stamp(config, "head")
    command.downgrade(config, BEFORE_TIMEZONE)
    assert "timezone" not in _columns(engine)
    with engine.begin() as connection:
        connection.execute(sa.text(
            "INSERT INTO meeting (id, owner_id, title, start_date, end_date, available_days,"
            " start_time, end_time, time_slot_minutes, created_at, updated_at)"
            " VALUES (:id, 'owner', 'm', '2024-02-05', '2024-02-09', '[0]', '09:00:00', '18:00:00', 30,"
            " '2026-11-14 00:00:00', '2026-11-14 00:00:00')"
        ), {"id": "a" * 32})

    command.upgrade(config, "f3a39109a3ef")

    column = _columns(engine)["timezone"]
    assert column["nullable"] is False
    assert column["default"] is None
    with engine.connect() as connection:
        assert connection.execute(sa.text("SELECT timezone FROM meeting")).scalar_one() == "UTC"

    command.downgrade(config, BEFORE_TIMEZONE)
    assert "timezone" not in _columns(engine)
    with engine.connect() as connection:
        assert connection.execute(sa.text("SELECT title FROM meeting")).scalar_one() == "m"


def test_upgrade_skips_column_that_create_all_already_made(engine_and_config) -> None:
    engine, config = engine_and_config
    command.stamp(config, BEFORE_TIMEZONE)

    command.upgrade(config, "head")

    assert _columns(engine)["timezone"]["nullable"] is False


def test_migrated_meeting_columns_match_model(engine_and_config, tmp_path: Path) -> None:
    migrated, config = engine_and_config
    command.stamp(config, "head")
    command.downgrade(config, BEFORE_TIMEZONE)
    command.upgrade(config, "head")
    modeled = sa.create_engine(f"sqlite:///{(tmp_path / 'modeled.db').resolve().as_posix()}")
    SQLModel.metadata.create_all(modeled)

    def shape(engine: sa.Engine) -> dict[str, tuple]:
        return {name: (c["nullable"], c["default"]) for name, c in _columns(engine).items()}

    assert shape(migrated) == shape(modeled)
    modeled.dispose()
