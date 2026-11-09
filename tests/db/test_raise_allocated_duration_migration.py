"""RUNNING·PAUSED 타이머의 allocated_duration을 elapsed_time으로 올리는 데이터 이전

alembic/versions/2026_11_09_1452-314620d41758_raise_allocated_duration_of_active_.py
"""

from __future__ import annotations

from datetime import datetime, timedelta
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
from app.core.constants import TimerStatus
from app.models.timer import TimerSession


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PREVIOUS_REVISION = "561746fec396"

# (status, allocated_duration, elapsed_time) -> 이전 뒤 allocated_duration
ROWS = {
    (TimerStatus.PAUSED, 1500, 2400): 2400,
    (TimerStatus.RUNNING, 1500, 2400): 2400,
    (TimerStatus.PAUSED, 1500, 1000): 1500,
    (TimerStatus.RUNNING, 1500, 1500): 1500,
    (TimerStatus.COMPLETED, 1500, 1633): 1500,
    (TimerStatus.CANCELLED, 1500, 2000): 1500,
}


def _alembic_config(monkeypatch: pytest.MonkeyPatch, database_url: str) -> Config:
    # alembic env.py는 실행 시점의 settings.DATABASE_URL을 읽는다
    import app.core.config as app_config
    monkeypatch.setattr(app_config.settings, "DATABASE_URL", database_url)

    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option(
        "script_location",
        (PROJECT_ROOT / "alembic").resolve().as_posix(),
    )
    return config


def _snapshot(engine: sa.Engine) -> dict[str, tuple[int, int]]:
    """title("status-원래 allocated-원래 elapsed") → (allocated_duration, elapsed_time)"""
    with Session(engine) as session:
        return {
            timer.title: (timer.allocated_duration, timer.elapsed_time)
            for timer in session.exec(select(TimerSession)).all()
        }


def test_upgrade_raises_overrun_active_timers_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = f"sqlite:///{(tmp_path / 'raise-allocated.db').resolve().as_posix()}"
    config = _alembic_config(monkeypatch, database_url)

    engine = sa.create_engine(database_url)
    SQLModel.metadata.create_all(engine)
    command.stamp(config, "head")
    command.downgrade(config, PREVIOUS_REVISION)

    started_at = datetime(2026, 11, 9, 3, 0) - timedelta(seconds=10)
    with Session(engine) as session:
        for status, allocated, elapsed in ROWS:
            session.add(TimerSession(
                owner_id="owner",
                title=f"{status.value}-{allocated}-{elapsed}",
                status=status,
                allocated_duration=allocated,
                elapsed_time=elapsed,
                started_at=started_at,
            ))
        session.commit()

    command.upgrade(config, "head")

    expected = {
        f"{status.value}-{allocated}-{elapsed}": (raised, elapsed)
        for (status, allocated, elapsed), raised in ROWS.items()
    }
    assert _snapshot(engine) == expected

    command.downgrade(config, PREVIOUS_REVISION)
    command.upgrade(config, "head")
    assert _snapshot(engine) == expected

    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    engine.dispose()
    heads = ScriptDirectory.from_config(config).get_heads()
    assert len(heads) == 1
    assert current == heads[0]
