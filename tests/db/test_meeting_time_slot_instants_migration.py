"""가능 시간 슬롯을 UTC 시각 구간으로 바꾸는 마이그레이션

alembic/versions/2026_11_14_1020-911321f82154_meeting_time_slot_utc_instants.py
"""

from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from sqlmodel import SQLModel

import app.models  # noqa: F401  # register every table in SQLModel.metadata
import app.models.holiday  # noqa: F401
from tests.db.conftest import database_url_for, migration_database

BEFORE_INSTANTS = "5fdfd93be2c3"
REVISION = "911321f82154"


@pytest.fixture(params=["sqlite", "postgresql"])
def database_url(request, tmp_path: Path) -> str:
    return database_url_for(request.param, tmp_path / "slots.db")


@pytest.fixture
def engine_and_config(database_url: str, monkeypatch: pytest.MonkeyPatch):
    with migration_database(monkeypatch, database_url) as engine_and_config:
        yield engine_and_config


@pytest.fixture
def legacy(engine_and_config):
    """슬롯이 날짜 + 시각이던 리비전까지 내린 DB와 미팅·참여자 하나"""
    engine, config = engine_and_config
    command.stamp(config, "head")
    command.downgrade(config, BEFORE_INSTANTS)
    with engine.begin() as connection:
        connection.execute(sa.text(
            "INSERT INTO meeting (id, owner_id, title, start_date, end_date, timezone, available_days,"
            " start_time, end_time, time_slot_minutes, created_at, updated_at)"
            " VALUES (:id, 'owner', 'm', '2024-02-05', '2024-02-09', 'UTC', '[0]', '09:00:00', '18:00:00', 30,"
            " '2026-11-14 00:00:00', '2026-11-14 00:00:00')"
        ), {"id": "a" * 32})
        connection.execute(sa.text(
            "INSERT INTO meeting_participant (id, meeting_id, user_id, display_name, created_at, updated_at)"
            " VALUES (:id, :meeting, 'u1', 'p', '2026-11-14 00:00:00', '2026-11-14 00:00:00')"
        ), {"id": "b" * 32, "meeting": "a" * 32})
    return engine, config


_PARTICIPANT = "b" * 32


def _hex(value) -> str:
    return value.hex if hasattr(value, "hex") else str(value).replace("-", "")


def _insert_legacy_slot(engine: sa.Engine, slot_id: str, slot_date: date, start: time, end: time) -> None:
    statement = sa.text(
        "INSERT INTO meeting_time_slot (id, participant_id, slot_date, start_time, end_time)"
        " VALUES (:id, :participant, :slot_date, :start, :end)"
    ).bindparams(
        sa.bindparam("slot_date", type_=sa.Date),
        sa.bindparam("start", type_=sa.Time),
        sa.bindparam("end", type_=sa.Time),
    )
    with engine.begin() as connection:
        connection.execute(statement, {
            "id": slot_id, "participant": _PARTICIPANT, "slot_date": slot_date, "start": start, "end": end,
        })


def _insert_slot(engine: sa.Engine, slot_id: str, start: datetime, end: datetime) -> None:
    statement = sa.text(
        "INSERT INTO meeting_time_slot (id, participant_id, start_time, end_time)"
        " VALUES (:id, :participant, :start, :end)"
    ).bindparams(sa.bindparam("start", type_=sa.DateTime), sa.bindparam("end", type_=sa.DateTime))
    with engine.begin() as connection:
        connection.execute(statement, {"id": slot_id, "participant": _PARTICIPANT, "start": start, "end": end})


def _slots(engine: sa.Engine) -> dict[str, tuple]:
    statement = sa.text("SELECT id, start_time, end_time FROM meeting_time_slot").columns(
        sa.column("id"), sa.column("start_time", sa.DateTime), sa.column("end_time", sa.DateTime),
    )
    with engine.connect() as connection:
        return {_hex(row.id): (row.start_time, row.end_time) for row in connection.execute(statement)}


def _legacy_slots(engine: sa.Engine) -> dict[str, tuple]:
    statement = sa.text("SELECT id, slot_date, start_time, end_time FROM meeting_time_slot").columns(
        sa.column("id"), sa.column("slot_date", sa.Date),
        sa.column("start_time", sa.Time), sa.column("end_time", sa.Time),
    )
    with engine.connect() as connection:
        return {
            _hex(row.id): (row.slot_date, row.start_time, row.end_time) for row in connection.execute(statement)
        }


def _columns(engine: sa.Engine) -> set[str]:
    return {c["name"] for c in sa.inspect(engine).get_columns("meeting_time_slot")}


def test_upgrade_reads_date_and_times_as_utc(legacy) -> None:
    engine, config = legacy
    _insert_legacy_slot(engine, "1" * 32, date(2024, 2, 5), time(9), time(12))
    _insert_legacy_slot(engine, "2" * 32, date(2024, 2, 6), time(0), time(23, 59))

    command.upgrade(config, REVISION)

    assert _columns(engine) == {"id", "participant_id", "start_time", "end_time"}
    assert _slots(engine) == {
        "1" * 32: (datetime(2024, 2, 5, 9), datetime(2024, 2, 5, 12)),
        "2" * 32: (datetime(2024, 2, 6, 0), datetime(2024, 2, 6, 23, 59)),
    }
    with pytest.raises(sa.exc.IntegrityError):
        _insert_slot(engine, "3" * 32, datetime(2024, 2, 5, 10), datetime(2024, 2, 5, 10))


def test_downgrade_restores_date_and_times(legacy) -> None:
    engine, config = legacy
    _insert_legacy_slot(engine, "1" * 32, date(2024, 2, 5), time(9), time(12))
    command.upgrade(config, REVISION)
    _insert_slot(engine, "2" * 32, datetime(2024, 2, 5, 22), datetime(2024, 2, 6, 0))
    _insert_slot(engine, "3" * 32, datetime(2024, 2, 5, 22), datetime(2024, 2, 7, 3))

    command.downgrade(config, BEFORE_INSTANTS)

    assert "slot_date" in _columns(engine)
    assert _legacy_slots(engine) == {
        "1" * 32: (date(2024, 2, 5), time(9), time(12)),
        # 끝이 다른 날짜면 그 날의 마지막 시각까지
        "2" * 32: (date(2024, 2, 5), time(22), time.max),
        "3" * 32: (date(2024, 2, 5), time(22), time.max),
    }
    assert "ix_meeting_time_slot_slot_date" in {i["name"] for i in sa.inspect(engine).get_indexes("meeting_time_slot")}

    command.upgrade(config, "head")
    assert _slots(engine)["1" * 32] == (datetime(2024, 2, 5, 9), datetime(2024, 2, 5, 12))


def test_upgrade_skips_table_that_create_all_already_made(engine_and_config) -> None:
    engine, config = engine_and_config
    command.stamp(config, BEFORE_INSTANTS)

    command.upgrade(config, "head")

    assert _columns(engine) == {"id", "participant_id", "start_time", "end_time"}


def test_migrated_schema_matches_model(legacy, tmp_path: Path) -> None:
    migrated, config = legacy
    command.upgrade(config, "head")
    modeled = sa.create_engine(f"sqlite:///{(tmp_path / 'modeled.db').resolve().as_posix()}")
    SQLModel.metadata.create_all(modeled)

    def shape(engine: sa.Engine) -> tuple:
        inspector = sa.inspect(engine)
        columns = {c["name"]: (str(c["type"]), c["nullable"]) for c in inspector.get_columns("meeting_time_slot")}
        indexes = {(i["name"], tuple(i["column_names"])) for i in inspector.get_indexes("meeting_time_slot")}
        foreign_keys = {
            (tuple(fk["constrained_columns"]), fk["referred_table"], (fk.get("options") or {}).get("ondelete"))
            for fk in inspector.get_foreign_keys("meeting_time_slot")
        }
        checks = {c["name"] for c in inspector.get_check_constraints("meeting_time_slot")}
        return columns, indexes, foreign_keys, checks

    if migrated.dialect.name == "sqlite":
        assert shape(migrated) == shape(modeled)
    else:
        # 컬럼 타입 이름은 방언마다 달라 컬럼은 NULL 허용만 비교한다
        migrated_shape, modeled_shape = shape(migrated), shape(modeled)
        assert {k: v[1] for k, v in migrated_shape[0].items()} == {k: v[1] for k, v in modeled_shape[0].items()}
        assert migrated_shape[1:] == modeled_shape[1:]
    modeled.dispose()
