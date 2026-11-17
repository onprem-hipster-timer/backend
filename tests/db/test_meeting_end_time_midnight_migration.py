"""미팅 end_time 00:00(하루의 끝)을 받는 마이그레이션

alembic/versions/2026_11_14_1010-5fdfd93be2c3_allow_meeting_end_time_midnight.py
"""

from __future__ import annotations

from datetime import date, time
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from sqlmodel import Session, SQLModel

import app.models  # noqa: F401  # register every table in SQLModel.metadata
import app.models.holiday  # noqa: F401
from app.models.meeting import Meeting, MeetingMode
from tests.db.conftest import database_url_for, migration_database

BEFORE_MIDNIGHT = "f3a39109a3ef"
REVISION = "5fdfd93be2c3"


@pytest.fixture(params=["sqlite", "postgresql"])
def database_url(request, tmp_path: Path) -> str:
    return database_url_for(request.param, tmp_path / "midnight.db")


@pytest.fixture
def engine_and_config(database_url: str, monkeypatch: pytest.MonkeyPatch):
    with migration_database(monkeypatch, database_url) as engine_and_config:
        yield engine_and_config


@pytest.fixture
def legacy(engine_and_config):
    """end_time 00:00을 받지 않던 리비전까지 내린 DB"""
    engine, config = engine_and_config
    command.stamp(config, "head")
    command.downgrade(config, BEFORE_MIDNIGHT)
    return engine, config


_INSERT = sa.text(
    "INSERT INTO meeting (id, owner_id, title, start_date, end_date, timezone, available_days,"
    " start_time, end_time, time_slot_minutes, created_at, updated_at)"
    " VALUES (:id, 'owner', 'm', '2024-02-05', '2024-02-09', 'UTC', '[0]', :start, :end, 30,"
    " '2026-11-14 00:00:00', '2026-11-14 00:00:00')"
)


def _insert(engine: sa.Engine, meeting_id: str, start: time, end: time) -> None:
    # ORM과 같은 형식으로 저장되도록 time 값을 바인딩한다
    statement = _INSERT.bindparams(sa.bindparam("start", type_=sa.Time), sa.bindparam("end", type_=sa.Time))
    with engine.begin() as connection:
        connection.execute(statement, {"id": meeting_id, "start": start, "end": end})


def _end_times(engine: sa.Engine) -> dict[str, time]:
    statement = sa.text("SELECT id, end_time FROM meeting").columns(
        sa.column("id", sa.String), sa.column("end_time", sa.Time),
    )
    with engine.connect() as connection:
        return {str(row.id).replace("-", ""): row.end_time for row in connection.execute(statement)}


def test_upgrade_accepts_midnight_end_and_still_rejects_reversed_range(legacy) -> None:
    engine, config = legacy
    with pytest.raises(sa.exc.IntegrityError):
        _insert(engine, "a" * 32, time(0), time(0))

    command.upgrade(config, REVISION)

    _insert(engine, "a" * 32, time(0), time(0))
    _insert(engine, "b" * 32, time(10), time(0))
    with pytest.raises(sa.exc.IntegrityError):
        _insert(engine, "c" * 32, time(10), time(9))
    with pytest.raises(sa.exc.IntegrityError):
        _insert(engine, "d" * 32, time(10), time(10))


def test_downgrade_moves_midnight_end_to_last_second(legacy) -> None:
    engine, config = legacy
    command.upgrade(config, REVISION)
    _insert(engine, "a" * 32, time(0), time(0))
    _insert(engine, "b" * 32, time(9), time(18))

    command.downgrade(config, BEFORE_MIDNIGHT)

    assert _end_times(engine) == {"a" * 32: time(23, 59, 59), "b" * 32: time(18)}
    with pytest.raises(sa.exc.IntegrityError):
        _insert(engine, "c" * 32, time(0), time(0))
    command.upgrade(config, "head")


def test_upgrade_skips_constraint_that_create_all_already_made(engine_and_config) -> None:
    engine, config = engine_and_config
    command.stamp(config, BEFORE_MIDNIGHT)

    command.upgrade(config, "head")

    with Session(engine) as session:
        session.add(Meeting(
            owner_id="owner", title="m", start_date=date(2024, 2, 5), end_date=date(2024, 2, 5), timezone="UTC",
            mode=MeetingMode.DAILY, start_time=time(0), end_time=time(0), time_slot_minutes=30,
        ))
        session.commit()


def test_migrated_meeting_checks_match_model(legacy, tmp_path: Path) -> None:
    migrated, config = legacy
    command.upgrade(config, "head")
    modeled = sa.create_engine(f"sqlite:///{(tmp_path / 'modeled.db').resolve().as_posix()}")
    SQLModel.metadata.create_all(modeled)

    def checks(engine: sa.Engine) -> dict[str, str]:
        return {c["name"]: c["sqltext"] for c in sa.inspect(engine).get_check_constraints("meeting")}

    if migrated.dialect.name == "sqlite":
        assert checks(migrated) == checks(modeled)
    else:
        # PostgreSQL은 제약 식을 자기 형식으로 다시 써서 돌려주므로 이름만 비교한다
        assert set(checks(migrated)) == set(checks(modeled))
    modeled.dispose()
