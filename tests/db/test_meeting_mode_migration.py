"""미팅의 답하는 방식(mode) 마이그레이션

alembic/versions/2026_11_17_1100-f10bc70bcb28_add_mode_to_meeting.py
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

BEFORE_MODE = "b5d9f3a7c2e4"
MODE = "f10bc70bcb28"

_INSERT_MEETING = sa.text(
    "INSERT INTO meeting (id, owner_id, title, start_date, end_date, timezone, available_days,"
    " start_time, end_time, time_slot_minutes, created_at, updated_at)"
    " VALUES (:id, 'owner', 'm', :start_date, :end_date, 'UTC', '[0, 1, 2, 3, 4, 5, 6]', :start_time, :end_time,"
    " 30, '2026-11-17 00:00:00', '2026-11-17 00:00:00')"
)

# (start_date, end_date, start_time, end_time) → mode
_ROWS = {
    "1" * 32: (("2024-02-05", "2024-02-11", "00:00:00", "00:00:00"), "weekly"),  # 7일, 하루 전체
    "2" * 32: (("2024-02-05", "2024-02-11", "00:00:00", "12:00:00"), "weekly"),  # 7일, 00:00 시작
    "3" * 32: (("2024-02-05", "2024-02-05", "00:00:00", "00:00:00"), "daily"),  # 하루
    "4" * 32: (("2024-02-05", "2024-02-10", "00:00:00", "00:00:00"), "daily"),  # 6일
    "5" * 32: (("2024-02-05", "2024-02-12", "00:00:00", "00:00:00"), "daily"),  # 8일
    "6" * 32: (("2024-02-05", "2024-05-05", "00:00:00", "18:00:00"), "daily"),  # 3개월, 00:00 시작
    "7" * 32: (("2024-02-05", "2024-02-11", "09:00:00", "18:00:00"), "hourly"),  # 7일, 09:00 시작
    "8" * 32: (("2024-02-05", "2024-02-05", "22:00:00", "00:00:00"), "hourly"),
    "9" * 32: (("2024-02-05", "2024-03-05", "00:30:00", "00:00:00"), "hourly"),
}


@pytest.fixture(params=["sqlite", "postgresql"])
def database_url(request, tmp_path: Path) -> str:
    return database_url_for(request.param, tmp_path / "meeting_mode.db")


@pytest.fixture
def engine_and_config(database_url: str, monkeypatch: pytest.MonkeyPatch):
    with migration_database(monkeypatch, database_url) as engine_and_config:
        yield engine_and_config


@pytest.fixture
def before_mode(engine_and_config):
    """mode가 없던 리비전까지 내린 DB"""
    engine, config = engine_and_config
    command.stamp(config, "head")
    command.downgrade(config, BEFORE_MODE)
    assert "mode" not in _columns(engine)
    return engine, config


def _columns(engine: sa.Engine) -> dict[str, dict]:
    return {c["name"]: c for c in sa.inspect(engine).get_columns("meeting")}


def _hex(value) -> str:
    return value.hex if hasattr(value, "hex") else str(value).replace("-", "")


def _modes(engine: sa.Engine) -> dict[str, str]:
    with engine.connect() as connection:
        return {_hex(mid): mode for mid, mode in connection.execute(sa.text("SELECT id, mode FROM meeting"))}


def test_upgrade_fills_mode_from_start_time_and_period(before_mode) -> None:
    engine, config = before_mode
    with engine.begin() as connection:
        for meeting_id, ((start_date, end_date, start_time, end_time), _) in _ROWS.items():
            connection.execute(_INSERT_MEETING, {
                "id": meeting_id, "start_date": start_date, "end_date": end_date,
                "start_time": start_time, "end_time": end_time,
            })

    command.upgrade(config, MODE)

    assert _modes(engine) == {meeting_id: mode for meeting_id, (_, mode) in _ROWS.items()}
    assert _columns(engine)["mode"]["nullable"] is False


def test_upgrade_without_meetings(before_mode) -> None:
    engine, config = before_mode

    command.upgrade(config, MODE)

    assert _columns(engine)["mode"]["nullable"] is False


def test_downgrade_drops_mode_and_keeps_meetings(before_mode) -> None:
    engine, config = before_mode
    with engine.begin() as connection:
        connection.execute(_INSERT_MEETING, {
            "id": "1" * 32, "start_date": "2024-02-05", "end_date": "2024-02-11",
            "start_time": "09:00:00", "end_time": "18:00:00",
        })
    command.upgrade(config, MODE)

    command.downgrade(config, BEFORE_MODE)

    assert "mode" not in _columns(engine)
    with engine.connect() as connection:
        assert connection.execute(sa.text("SELECT title FROM meeting")).scalar_one() == "m"

    command.upgrade(config, "head")
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    assert ScriptDirectory.from_config(config).get_heads() == [current]


def test_upgrade_skips_column_that_create_all_already_made(engine_and_config) -> None:
    engine, config = engine_and_config
    command.stamp(config, BEFORE_MODE)

    command.upgrade(config, "head")

    assert _columns(engine)["mode"]["nullable"] is False


def test_migrated_meeting_columns_match_model(before_mode, tmp_path: Path) -> None:
    migrated, config = before_mode
    command.upgrade(config, "head")
    modeled = sa.create_engine(f"sqlite:///{(tmp_path / 'modeled.db').resolve().as_posix()}")
    SQLModel.metadata.create_all(modeled)

    def shape(engine: sa.Engine) -> dict[str, bool]:
        return {name: c["nullable"] for name, c in _columns(engine).items()}

    assert shape(migrated) == shape(modeled)
    if migrated.dialect.name == "sqlite":
        assert str(_columns(migrated)["mode"]["type"]) == str(_columns(modeled)["mode"]["type"])
    modeled.dispose()
