"""공휴일 하루 끝을 다음 날 00:00으로 옮기는 데이터 이전

alembic/versions/2026_11_14_0910-a9e1c7d3f5b2_move_holiday_day_ends_to_midnight.py
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlmodel import Session, SQLModel, select

import app.models  # noqa: F401  # register every table in SQLModel.metadata
import app.models.holiday  # noqa: F401
from app.models.holiday import HolidayModel

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PREVIOUS_REVISION = "f2b6d8a4c0e7"
_TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")

# dateName -> (start_date, 이전 전 end_date, upgrade 뒤 end_date, downgrade 뒤 end_date)
ROWS = {
    "one-day": (
        datetime(2023, 12, 31, 15), datetime(2024, 1, 1, 14, 59, 59, 999999),
        datetime(2024, 1, 1, 15), datetime(2024, 1, 1, 14, 59, 59, 999999),
    ),
    "two-days": (
        datetime(2024, 2, 8, 15), datetime(2024, 2, 10, 14, 59, 59, 999999),
        datetime(2024, 2, 10, 15), datetime(2024, 2, 10, 14, 59, 59, 999999),
    ),
    "seconds": (
        datetime(2024, 3, 1, 15), datetime(2024, 3, 2, 14, 59, 59),
        datetime(2024, 3, 2, 14, 59, 59), datetime(2024, 3, 2, 14, 59, 59),
    ),
    "partial-day": (
        datetime(2024, 5, 5, 15), datetime(2024, 5, 6, 16, 59, 59, 999999),
        datetime(2024, 5, 6, 16, 59, 59, 999999), datetime(2024, 5, 6, 16, 59, 59, 999999),
    ),
    "already-midnight": (
        datetime(2024, 6, 5, 15), datetime(2024, 6, 6, 15),
        datetime(2024, 6, 6, 15), datetime(2024, 6, 6, 14, 59, 59, 999999),
    ),
}


def _alembic_config(monkeypatch: pytest.MonkeyPatch, database_url: str) -> Config:
    import app.core.config as app_config
    monkeypatch.setattr(app_config.settings, "DATABASE_URL", database_url)

    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", (PROJECT_ROOT / "alembic").resolve().as_posix())
    return config


def _snapshot(engine: sa.Engine) -> dict[str, datetime]:
    with Session(engine) as session:
        return {h.dateName: h.end_date for h in session.exec(select(HolidayModel)).all()}


def _expected(stage: int) -> dict[str, datetime]:
    return {name: row[stage] for name, row in ROWS.items()}


@pytest.mark.parametrize(
    "database_url",
    [
        pytest.param("sqlite", id="sqlite"),
        pytest.param(
            _TEST_DATABASE_URL,
            id="postgresql",
            marks=pytest.mark.skipif(
                not _TEST_DATABASE_URL.startswith("postgresql"),
                reason="requires PostgreSQL via TEST_DATABASE_URL",
            ),
        ),
    ],
)
def test_day_end_rows_move_to_midnight_and_back(
    database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if database_url == "sqlite":
        database_url = f"sqlite:///{(tmp_path / 'holiday-day-end.db').resolve().as_posix()}"
    config = _alembic_config(monkeypatch, database_url)
    engine = sa.create_engine(database_url)
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)

    try:
        command.stamp(config, "head")
        command.downgrade(config, PREVIOUS_REVISION)
        with Session(engine) as session:
            for name, (start, end, _, _) in ROWS.items():
                session.add(HolidayModel(
                    start_date=start, end_date=end, dateName=name, isHoliday=True, dateKind="국경일",
                ))
            session.commit()

        command.upgrade(config, "head")
        assert _snapshot(engine) == _expected(2)

        command.downgrade(config, PREVIOUS_REVISION)
        assert _snapshot(engine) == _expected(3)
    finally:
        with engine.begin() as connection:
            connection.execute(sa.text("DROP TABLE IF EXISTS alembic_version"))
        SQLModel.metadata.drop_all(engine)
        engine.dispose()


def test_upgrade_without_holidays_table(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = f"sqlite:///{(tmp_path / 'no-holidays.db').resolve().as_posix()}"
    config = _alembic_config(monkeypatch, database_url)
    engine = sa.create_engine(database_url)
    SQLModel.metadata.create_all(engine)
    HolidayModel.__table__.drop(engine)

    command.stamp(config, "head")
    command.downgrade(config, PREVIOUS_REVISION)
    command.upgrade(config, "head")
    engine.dispose()
