"""가능 시간 구간의 종류(kind) 마이그레이션

alembic/versions/2026_11_17_1130-9d3b480a27c9_add_kind_to_meeting_time_slot.py
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

BEFORE_KIND = "88d59fb76aa6"
KIND = "9d3b480a27c9"

_MEETING = "a" * 32
_PARTICIPANT = "b" * 32
_INSERT_SLOT = sa.text(
    "INSERT INTO meeting_time_slot (id, participant_id, start_time, end_time)"
    " VALUES (:id, :participant, '2024-02-05 09:00:00', '2024-02-05 10:00:00')"
)
_INSERT_SLOT_WITH_KIND = sa.text(
    "INSERT INTO meeting_time_slot (id, participant_id, start_time, end_time, kind)"
    " VALUES (:id, :participant, '2024-02-05 10:00:00', '2024-02-05 11:00:00', :kind)"
)


@pytest.fixture(params=["sqlite", "postgresql"])
def database_url(request, tmp_path: Path) -> str:
    return database_url_for(request.param, tmp_path / "slot_kind.db")


@pytest.fixture
def engine_and_config(database_url: str, monkeypatch: pytest.MonkeyPatch):
    with migration_database(monkeypatch, database_url) as engine_and_config:
        yield engine_and_config


@pytest.fixture
def before_kind(engine_and_config):
    """kind가 없던 리비전까지 내린 DB와 미팅·참여자 하나"""
    engine, config = engine_and_config
    command.stamp(config, "head")
    command.downgrade(config, BEFORE_KIND)
    assert "kind" not in _columns(engine)
    with engine.begin() as connection:
        connection.execute(sa.text(
            "INSERT INTO meeting (id, owner_id, title, start_date, end_date, excluded_dates, timezone, mode,"
            " start_time, end_time, time_slot_minutes, created_at, updated_at)"
            " VALUES (:id, 'owner', 'm', '2024-02-05', '2024-02-09', '[]', 'UTC', 'hourly', '09:00:00', '18:00:00',"
            " 30, '2026-11-17 00:00:00', '2026-11-17 00:00:00')"
        ), {"id": _MEETING})
        connection.execute(sa.text(
            "INSERT INTO meeting_participant (id, meeting_id, user_id, display_name, created_at, updated_at)"
            " VALUES (:id, :meeting, 'u1', 'p', '2026-11-17 00:00:00', '2026-11-17 00:00:00')"
        ), {"id": _PARTICIPANT, "meeting": _MEETING})
    return engine, config


def _columns(engine: sa.Engine) -> dict[str, dict]:
    return {c["name"]: c for c in sa.inspect(engine).get_columns("meeting_time_slot")}


def _hex(value) -> str:
    return value.hex if hasattr(value, "hex") else str(value).replace("-", "")


def _kinds(engine: sa.Engine) -> dict[str, str]:
    with engine.connect() as connection:
        return {_hex(sid): kind for sid, kind in connection.execute(sa.text("SELECT id, kind FROM meeting_time_slot"))}


def test_existing_slots_become_available(before_kind) -> None:
    engine, config = before_kind
    with engine.begin() as connection:
        connection.execute(_INSERT_SLOT, {"id": "1" * 32, "participant": _PARTICIPANT})
        connection.execute(_INSERT_SLOT, {"id": "2" * 32, "participant": _PARTICIPANT})

    command.upgrade(config, KIND)

    assert _kinds(engine) == {"1" * 32: "available", "2" * 32: "available"}
    assert _columns(engine)["kind"]["nullable"] is False
    with engine.begin() as connection:
        connection.execute(_INSERT_SLOT, {"id": "3" * 32, "participant": _PARTICIPANT})
    assert _kinds(engine)["3" * 32] == "available"


def test_downgrade_deletes_unavailable_slots_and_drops_kind(before_kind) -> None:
    engine, config = before_kind
    command.upgrade(config, KIND)
    with engine.begin() as connection:
        connection.execute(_INSERT_SLOT_WITH_KIND, {"id": "1" * 32, "participant": _PARTICIPANT, "kind": "available"})
        connection.execute(_INSERT_SLOT_WITH_KIND, {"id": "2" * 32, "participant": _PARTICIPANT, "kind": "unavailable"})

    command.downgrade(config, BEFORE_KIND)

    assert "kind" not in _columns(engine)
    with engine.connect() as connection:
        ids = {_hex(sid) for (sid,) in connection.execute(sa.text("SELECT id FROM meeting_time_slot"))}
    assert ids == {"1" * 32}

    command.upgrade(config, "head")
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    assert ScriptDirectory.from_config(config).get_heads() == [current]


def test_upgrade_skips_column_that_create_all_already_made(engine_and_config) -> None:
    engine, config = engine_and_config
    command.stamp(config, BEFORE_KIND)

    command.upgrade(config, "head")

    assert _columns(engine)["kind"]["nullable"] is False


def test_migrated_time_slot_columns_match_model(before_kind, tmp_path: Path) -> None:
    migrated, config = before_kind
    command.upgrade(config, "head")
    modeled = sa.create_engine(f"sqlite:///{(tmp_path / 'modeled.db').resolve().as_posix()}")
    SQLModel.metadata.create_all(modeled)

    def shape(engine: sa.Engine) -> dict[str, tuple]:
        return {name: (str(c["type"]), c["nullable"]) for name, c in _columns(engine).items()}

    if migrated.dialect.name == "sqlite":
        assert shape(migrated) == shape(modeled)
        assert _columns(migrated)["kind"]["default"] == _columns(modeled)["kind"]["default"]
    else:
        assert {k: v[1] for k, v in shape(migrated).items()} == {k: v[1] for k, v in shape(modeled).items()}
    modeled.dispose()
