"""일정 하루 끝을 다음 날 00:00으로 옮기는 데이터 이전

alembic/versions/2026_11_14_0900-f2b6d8a4c0e7_move_schedule_day_ends_to_midnight.py
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlmodel import Session, SQLModel, select

import app.models  # noqa: F401  # register every table in SQLModel.metadata
import app.models.holiday  # noqa: F401
from app.models.schedule import Schedule, ScheduleException

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PREVIOUS_REVISION = "e7f3a9c5b1d8"
_TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")

# title -> (start_time, 이전 전 end_time, upgrade 뒤 end_time, downgrade 뒤 end_time)
ROWS = {
    "one-day": (
        datetime(2024, 3, 10), datetime(2024, 3, 10, 23, 59),
        datetime(2024, 3, 11), datetime(2024, 3, 10, 23, 59),
    ),
    "three-days": (
        datetime(2024, 3, 10), datetime(2024, 3, 12, 23, 59),
        datetime(2024, 3, 13), datetime(2024, 3, 12, 23, 59),
    ),
    "kst-day": (
        datetime(2024, 3, 9, 15), datetime(2024, 3, 10, 14, 59),
        datetime(2024, 3, 10, 15), datetime(2024, 3, 10, 14, 59),
    ),
    "two-hours": (
        datetime(2024, 3, 10, 9), datetime(2024, 3, 10, 10, 59),
        datetime(2024, 3, 10, 10, 59), datetime(2024, 3, 10, 10, 59),
    ),
    "seconds": (
        datetime(2024, 3, 10), datetime(2024, 3, 10, 23, 59, 30),
        datetime(2024, 3, 10, 23, 59, 30), datetime(2024, 3, 10, 23, 59, 30),
    ),
    "microseconds": (
        datetime(2024, 3, 10), datetime(2024, 3, 10, 23, 59, 59, 999999),
        datetime(2024, 3, 10, 23, 59, 59, 999999), datetime(2024, 3, 10, 23, 59, 59, 999999),
    ),
    "already-midnight": (
        datetime(2024, 3, 10), datetime(2024, 3, 11),
        datetime(2024, 3, 11), datetime(2024, 3, 10, 23, 59),
    ),
}


def _alembic_config(monkeypatch: pytest.MonkeyPatch, database_url: str) -> Config:
    import app.core.config as app_config
    monkeypatch.setattr(app_config.settings, "DATABASE_URL", database_url)

    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", (PROJECT_ROOT / "alembic").resolve().as_posix())
    return config


def _database_urls() -> list:
    urls = [pytest.param("sqlite", id="sqlite")]
    urls.append(pytest.param(
        _TEST_DATABASE_URL,
        id="postgresql",
        marks=pytest.mark.skipif(
            not _TEST_DATABASE_URL.startswith("postgresql"),
            reason="requires PostgreSQL via TEST_DATABASE_URL",
        ),
    ))
    return urls


def _snapshot(engine: sa.Engine) -> dict[str, datetime | None]:
    with Session(engine) as session:
        schedules = {s.title: s.end_time for s in session.exec(select(Schedule)).all()}
        exceptions = {
            f"exception-{e.title}": e.end_time
            for e in session.exec(select(ScheduleException)).all()
        }
    return schedules | exceptions


def _seed(engine: sa.Engine) -> None:
    with Session(engine) as session:
        parent = None
        for title, (start, end, _, _) in ROWS.items():
            schedule = Schedule(owner_id="owner", title=title, start_time=start, end_time=end)
            session.add(schedule)
            parent = parent or schedule
        session.flush()
        session.add(ScheduleException(
            owner_id="owner", parent_id=parent.id, exception_date=datetime(2024, 3, 17),
            title="one-day", start_time=datetime(2024, 3, 17), end_time=datetime(2024, 3, 17, 23, 59),
        ))
        session.add(ScheduleException(
            owner_id="owner", parent_id=parent.id, exception_date=datetime(2024, 3, 24),
            title="deleted", is_deleted=True,
        ))
        session.commit()


def _expected(stage: int) -> dict[str, datetime | None]:
    expected: dict[str, datetime | None] = {title: row[stage] for title, row in ROWS.items()}
    expected["exception-one-day"] = datetime(2024, 3, 18) if stage == 2 else datetime(2024, 3, 17, 23, 59)
    expected["exception-deleted"] = None
    return expected


@pytest.mark.parametrize("database_url", _database_urls())
def test_day_end_rows_move_to_midnight_and_back(
    database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if database_url == "sqlite":
        database_url = f"sqlite:///{(tmp_path / 'schedule-day-end.db').resolve().as_posix()}"
    config = _alembic_config(monkeypatch, database_url)
    engine = sa.create_engine(database_url)
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)

    try:
        command.stamp(config, "head")
        command.downgrade(config, PREVIOUS_REVISION)
        _seed(engine)
        assert _snapshot(engine) == _expected(1)

        command.upgrade(config, "head")
        assert _snapshot(engine) == _expected(2)

        command.downgrade(config, PREVIOUS_REVISION)
        assert _snapshot(engine) == _expected(3)

        command.upgrade(config, "head")
        with engine.connect() as connection:
            current = MigrationContext.configure(connection).get_current_revision()
        assert current == ScriptDirectory.from_config(config).get_heads()[0]
    finally:
        with engine.begin() as connection:
            connection.execute(sa.text("DROP TABLE IF EXISTS alembic_version"))
        SQLModel.metadata.drop_all(engine)
        engine.dispose()
