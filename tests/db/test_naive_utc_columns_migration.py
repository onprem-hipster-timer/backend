"""Migration that turns timestamptz columns into UTC naive columns.

The PostgreSQL test builds the schema the way the deployment bootstrap does
(``create_all`` with every DateTime column timezone-aware, then ``stamp``)
and checks that the stored UTC instants survive the type change.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlmodel import SQLModel

import app.models  # noqa: F401  # register every table in SQLModel.metadata
import app.models.holiday  # noqa: F401
from app.core.constants import TimerStatus


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PREVIOUS_REVISION = "c4d7e8f1a2b3"

_TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")


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


def test_upgrade_from_previous_revision_on_sqlite_reaches_single_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = f"sqlite:///{(tmp_path / 'naive-utc.db').resolve().as_posix()}"
    config = _alembic_config(monkeypatch, database_url)

    engine = sa.create_engine(database_url)
    SQLModel.metadata.create_all(engine)
    engine.dispose()

    command.stamp(config, "head")
    command.downgrade(config, PREVIOUS_REVISION)
    command.upgrade(config, "head")

    engine = sa.create_engine(database_url)
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    engine.dispose()
    heads = ScriptDirectory.from_config(config).get_heads()

    assert len(heads) == 1
    assert current == heads[0]


def _app_table_names() -> set[str]:
    """app.models 패키지의 테이블 (다른 테스트가 등록한 테스트용 테이블은 제외)"""
    return {
        mapper.class_.__table__.name
        for mapper in SQLModel._sa_registry.mappers
        if mapper.class_.__module__.startswith("app.models.")
    }


def _bootstrap_metadata() -> sa.MetaData:
    """Today's app tables with every DateTime column timezone-aware."""
    app_tables = _app_table_names()
    metadata = sa.MetaData()
    for table in SQLModel.metadata.sorted_tables:
        if table.name not in app_tables:
            continue
        copied = table.to_metadata(metadata)
        for column in copied.columns:
            if isinstance(column.type, sa.DateTime):
                column.type = sa.DateTime(timezone=True)
    return metadata


def _with_session_timezone(database_url: str, tz_name: str) -> str:
    # 세션 TimeZone이 UTC가 아니어야 단순 캐스트와 UTC 기준 변환이 구별된다
    url = sa.make_url(database_url).update_query_dict(
        {"options": f"-c timezone={tz_name}"}
    )
    return url.render_as_string(hide_password=False)


def _timestamp_column_types(
    engine: sa.Engine,
    metadata: sa.MetaData,
) -> dict[tuple[str, str], str]:
    with engine.connect() as connection:
        rows = connection.execute(
            sa.text(
                "SELECT table_name, column_name, data_type"
                " FROM information_schema.columns"
                " WHERE table_schema = current_schema()"
                " AND data_type LIKE 'timestamp%'"
            )
        )
        return {
            (table, column): data_type
            for table, column, data_type in rows
            if table in metadata.tables
        }


def _drop_schema(engine: sa.Engine, metadata: sa.MetaData) -> None:
    metadata.drop_all(engine)
    with engine.begin() as connection:
        connection.execute(sa.text("DROP TABLE IF EXISTS alembic_version"))


@pytest.mark.integration
@pytest.mark.skipif(
    not _TEST_DATABASE_URL.startswith("postgresql"),
    reason="requires PostgreSQL via TEST_DATABASE_URL for timestamptz columns",
)
def test_upgrade_converts_timestamptz_to_naive_utc_and_downgrade_restores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _with_session_timezone(_TEST_DATABASE_URL, "Asia/Seoul")
    config = _alembic_config(monkeypatch, database_url)
    metadata = _bootstrap_metadata()
    timers = metadata.tables["timersession"]
    started_at = datetime(2026, 11, 8, 3, 0, tzinfo=timezone.utc)
    timer_id = uuid4()

    engine = sa.create_engine(database_url)
    _drop_schema(engine, metadata)
    metadata.create_all(engine)

    def stored_started_at() -> datetime:
        with engine.connect() as connection:
            return connection.scalar(
                sa.select(timers.c.started_at).where(timers.c.id == timer_id)
            )

    try:
        command.stamp(config, "head")
        command.downgrade(config, PREVIOUS_REVISION)
        with engine.begin() as connection:
            connection.execute(
                timers.insert().values(
                    id=timer_id,
                    owner_id="owner",
                    allocated_duration=1500,
                    status=TimerStatus.RUNNING,
                    started_at=started_at,
                )
            )
        before = _timestamp_column_types(engine, metadata)
        assert before
        assert set(before.values()) == {"timestamp with time zone"}

        command.upgrade(config, "head")

        after_upgrade = _timestamp_column_types(engine, metadata)
        assert after_upgrade.keys() == before.keys()
        assert set(after_upgrade.values()) == {"timestamp without time zone"}, sorted(k for k, v in after_upgrade.items() if v != "timestamp without time zone")
        naive = stored_started_at()
        assert naive.tzinfo is None
        assert naive == started_at.replace(tzinfo=None)

        command.downgrade(config, PREVIOUS_REVISION)

        after_downgrade = _timestamp_column_types(engine, metadata)
        assert after_downgrade == before
        assert stored_started_at() == started_at
    finally:
        _drop_schema(engine, metadata)
        engine.dispose()
