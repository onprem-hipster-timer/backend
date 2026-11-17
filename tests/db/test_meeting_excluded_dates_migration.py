"""미팅의 요일(available_days)을 제외 날짜(excluded_dates)로 바꾸는 마이그레이션

alembic/versions/2026_11_17_1110-05f01afca5ea_add_excluded_dates_to_meeting.py
alembic/versions/2026_11_17_1120-88d59fb76aa6_drop_available_days_from_meeting.py
"""

from __future__ import annotations

from datetime import date
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

BEFORE_EXCLUDED = "f10bc70bcb28"
EXCLUDED = "05f01afca5ea"
DROP_AVAILABLE_DAYS = "88d59fb76aa6"


@pytest.fixture(params=["sqlite", "postgresql"])
def database_url(request, tmp_path: Path) -> str:
    return database_url_for(request.param, tmp_path / "excluded_dates.db")


@pytest.fixture
def engine_and_config(database_url: str, monkeypatch: pytest.MonkeyPatch):
    with migration_database(monkeypatch, database_url) as engine_and_config:
        yield engine_and_config


def _columns(engine: sa.Engine) -> dict[str, dict]:
    return {c["name"]: c for c in sa.inspect(engine).get_columns("meeting")}


def _hex(value) -> str:
    return value.hex if hasattr(value, "hex") else str(value).replace("-", "")


def _single_head(engine: sa.Engine, config) -> None:
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    assert ScriptDirectory.from_config(config).get_heads() == [current]


def _select(engine: sa.Engine, *columns: sa.ColumnClause) -> dict[str, tuple]:
    meeting = sa.table("meeting", sa.column("id"), *columns)
    with engine.connect() as connection:
        rows = connection.execute(sa.select(meeting.c.id, *(meeting.c[c.name] for c in columns))).all()
    return {_hex(row[0]): tuple(row[1:]) for row in rows}


def _period() -> tuple[sa.ColumnClause, sa.ColumnClause]:
    return sa.column("start_date", sa.Date()), sa.column("end_date", sa.Date())


# ============ available_days → excluded_dates ============

_INSERT_WITH_DAYS = sa.text(
    "INSERT INTO meeting (id, owner_id, title, start_date, end_date, timezone, mode, available_days,"
    " start_time, end_time, time_slot_minutes, created_at, updated_at)"
    " VALUES (:id, 'owner', 'm', :start_date, :end_date, 'UTC', :mode, :days, '09:00:00', '18:00:00', 30,"
    " '2026-11-17 00:00:00', '2026-11-17 00:00:00')"
)

# (start_date, end_date, available_days) → (start_date, end_date, excluded_dates)
_BACKFILL = {
    # 목~수 중 월·수·금: 첫 금요일부터, 사이의 토·일·화를 뺀다
    "1" * 32: (
        ("2024-02-01", "2024-02-07", [0, 2, 4]),
        ("2024-02-02", "2024-02-07", ["2024-02-03", "2024-02-04", "2024-02-06"]),
    ),
    # 화요일 세 번 (2주): 사이의 화요일이 아닌 날을 뺀다
    "2" * 32: (
        ("2024-02-06", "2024-02-20", [1]),
        ("2024-02-06", "2024-02-20", [
            "2024-02-07", "2024-02-08", "2024-02-09", "2024-02-10", "2024-02-11", "2024-02-12",
            "2024-02-14", "2024-02-15", "2024-02-16", "2024-02-17", "2024-02-18", "2024-02-19",
        ]),
    ),
    # 월~수 3주 중 화요일만: 앞뒤를 줄인다
    "3" * 32: (
        ("2024-02-05", "2024-02-21", [1]),
        ("2024-02-06", "2024-02-20", [
            "2024-02-07", "2024-02-08", "2024-02-09", "2024-02-10", "2024-02-11", "2024-02-12",
            "2024-02-14", "2024-02-15", "2024-02-16", "2024-02-17", "2024-02-18", "2024-02-19",
        ]),
    ),
    # 7일, 모든 요일
    "4" * 32: (("2024-02-05", "2024-02-11", [0, 1, 2, 3, 4, 5, 6]), ("2024-02-05", "2024-02-11", [])),
    # 하루
    "5" * 32: (("2024-02-05", "2024-02-05", [0]), ("2024-02-05", "2024-02-05", [])),
    # 토~일 9일 중 평일: 앞뒤 주말을 줄인다
    "6" * 32: (("2024-02-03", "2024-02-11", [0, 1, 2, 3, 4]), ("2024-02-05", "2024-02-09", [])),
    # 2주 평일: 사이의 주말을 뺀다
    "7" * 32: (("2024-02-05", "2024-02-16", [0, 1, 2, 3, 4]), ("2024-02-05", "2024-02-16", ["2024-02-10", "2024-02-11"])),
    # 미팅 날짜가 없는 기간은 그대로 둔다
    "8" * 32: (("2024-02-06", "2024-02-06", [0]), ("2024-02-06", "2024-02-06", [])),
    "9" * 32: (("2024-02-06", "2024-02-08", [0]), ("2024-02-06", "2024-02-08", [])),
    "a" * 32: (("2024-02-05", "2024-02-09", []), ("2024-02-05", "2024-02-09", [])),
}


@pytest.fixture
def before_excluded(engine_and_config):
    """excluded_dates가 없던 리비전까지 내린 DB"""
    engine, config = engine_and_config
    command.stamp(config, "head")
    command.downgrade(config, BEFORE_EXCLUDED)
    assert "excluded_dates" not in _columns(engine)
    assert "available_days" in _columns(engine)
    return engine, config


def _insert_with_days(engine: sa.Engine, rows: dict) -> None:
    statement = _INSERT_WITH_DAYS.bindparams(sa.bindparam("days", type_=sa.JSON()))
    with engine.begin() as connection:
        for meeting_id, ((start_date, end_date, days), _) in rows.items():
            connection.execute(statement, {
                "id": meeting_id, "start_date": start_date, "end_date": end_date, "mode": "hourly", "days": days,
            })


def test_upgrade_fills_excluded_dates_and_shrinks_period(before_excluded) -> None:
    engine, config = before_excluded
    _insert_with_days(engine, _BACKFILL)

    command.upgrade(config, EXCLUDED)

    rows = _select(engine, *_period(), sa.column("excluded_dates", sa.JSON()), sa.column("mode"))
    assert rows == {
        meeting_id: (date.fromisoformat(start), date.fromisoformat(end), excluded, "hourly")
        for meeting_id, (_, (start, end, excluded)) in _BACKFILL.items()
    }
    assert _columns(engine)["excluded_dates"]["nullable"] is False


def test_downgrade_drops_excluded_dates_and_keeps_shrunk_period(before_excluded) -> None:
    engine, config = before_excluded
    _insert_with_days(engine, {"1" * 32: _BACKFILL["1" * 32]})
    command.upgrade(config, EXCLUDED)

    command.downgrade(config, BEFORE_EXCLUDED)

    assert "excluded_dates" not in _columns(engine)
    rows = _select(engine, *_period(), sa.column("available_days", sa.JSON()))
    assert rows == {"1" * 32: (date(2024, 2, 2), date(2024, 2, 7), [0, 2, 4])}

    command.upgrade(config, "head")
    _single_head(engine, config)


# ============ available_days 없애기 ============

_INSERT_WITH_EXCLUDED = sa.text(
    "INSERT INTO meeting (id, owner_id, title, start_date, end_date, timezone, mode, excluded_dates,"
    " start_time, end_time, time_slot_minutes, created_at, updated_at)"
    " VALUES (:id, 'owner', 'm', :start_date, :end_date, 'UTC', 'daily', :excluded, '00:00:00', '00:00:00', 1440,"
    " '2026-11-17 00:00:00', '2026-11-17 00:00:00')"
)

_TUESDAYS_ONLY = [
    "2024-02-07", "2024-02-08", "2024-02-09", "2024-02-10", "2024-02-11", "2024-02-12",
    "2024-02-14", "2024-02-15", "2024-02-16", "2024-02-17", "2024-02-18", "2024-02-19",
]

# (start_date, end_date, excluded_dates) → available_days
_RESTORE = {
    "1" * 32: (("2024-02-02", "2024-02-07", ["2024-02-03", "2024-02-04", "2024-02-06"]), [0, 2, 4]),
    "2" * 32: (("2024-02-06", "2024-02-20", _TUESDAYS_ONLY), [1]),
    "3" * 32: (("2024-02-05", "2024-02-05", []), [0]),
    "4" * 32: (("2024-02-05", "2024-02-11", []), [0, 1, 2, 3, 4, 5, 6]),
    # 가운데 화요일만 뺀 2주: 화요일이 미팅 날짜에도 있어 화요일이 들어간다
    "5" * 32: (("2024-02-06", "2024-02-20", ["2024-02-13"]), [0, 1, 2, 3, 4, 5, 6]),
}


@pytest.fixture
def at_drop(engine_and_config):
    """available_days를 없앤 리비전의 DB"""
    engine, config = engine_and_config
    command.stamp(config, "head")
    command.downgrade(config, DROP_AVAILABLE_DAYS)
    return engine, config


def _insert_with_excluded(engine: sa.Engine, rows: dict) -> None:
    statement = _INSERT_WITH_EXCLUDED.bindparams(sa.bindparam("excluded", type_=sa.JSON()))
    with engine.begin() as connection:
        for meeting_id, ((start_date, end_date, excluded), _) in rows.items():
            connection.execute(statement, {
                "id": meeting_id, "start_date": start_date, "end_date": end_date, "excluded": excluded,
            })


def test_upgrade_drops_available_days(before_excluded) -> None:
    engine, config = before_excluded
    _insert_with_days(engine, {"1" * 32: _BACKFILL["1" * 32]})

    command.upgrade(config, DROP_AVAILABLE_DAYS)

    assert "available_days" not in _columns(engine)
    rows = _select(engine, *_period(), sa.column("excluded_dates", sa.JSON()))
    assert rows == {"1" * 32: (date(2024, 2, 2), date(2024, 2, 7), ["2024-02-03", "2024-02-04", "2024-02-06"])}


def test_downgrade_restores_available_days_from_meeting_dates(at_drop) -> None:
    engine, config = at_drop
    _insert_with_excluded(engine, _RESTORE)

    command.downgrade(config, EXCLUDED)

    assert _columns(engine)["available_days"]["nullable"] is False
    rows = _select(engine, sa.column("available_days", sa.JSON()), sa.column("excluded_dates", sa.JSON()))
    assert rows == {
        meeting_id: (days, excluded) for meeting_id, ((_, _, excluded), days) in _RESTORE.items()
    }

    command.downgrade(config, BEFORE_EXCLUDED)
    command.upgrade(config, "head")
    _single_head(engine, config)
    # 가운데 화요일만 뺀 미팅은 요일로 되돌린 뒤 다시 올리면 그 화요일도 미팅 날짜다
    rows = _select(engine, *_period(), sa.column("excluded_dates", sa.JSON()))
    assert rows["5" * 32] == (date(2024, 2, 6), date(2024, 2, 20), [])
    assert rows["2" * 32] == (date(2024, 2, 6), date(2024, 2, 20), _TUESDAYS_ONLY)


def test_upgrade_skips_columns_that_create_all_already_made(engine_and_config) -> None:
    engine, config = engine_and_config
    command.stamp(config, BEFORE_EXCLUDED)

    command.upgrade(config, "head")

    columns = _columns(engine)
    assert columns["excluded_dates"]["nullable"] is False
    assert "available_days" not in columns


def test_migrated_meeting_columns_match_model(before_excluded, tmp_path: Path) -> None:
    migrated, config = before_excluded
    _insert_with_days(migrated, {"1" * 32: _BACKFILL["1" * 32]})
    command.upgrade(config, "head")
    modeled = sa.create_engine(f"sqlite:///{(tmp_path / 'modeled.db').resolve().as_posix()}")
    SQLModel.metadata.create_all(modeled)

    def shape(engine: sa.Engine) -> dict[str, bool]:
        return {name: c["nullable"] for name, c in _columns(engine).items()}

    assert shape(migrated) == shape(modeled)
    if migrated.dialect.name == "sqlite":
        assert str(_columns(migrated)["excluded_dates"]["type"]) == str(_columns(modeled)["excluded_dates"]["type"])
    modeled.dispose()
