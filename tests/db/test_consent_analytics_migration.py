"""consent에 사용성 분석 동의 컬럼을 더하는 마이그레이션

alembic/versions/2026_11_18_1200-34f0c570658d_add_analytics_to_consent.py
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from tests.db.conftest import database_url_for, migration_database

PREVIOUS_REVISION = "b3e7c1d9f4a2"
ANALYTICS_REVISION = "34f0c570658d"
ANALYTICS_COLUMNS = {"analytics", "analytics_updated_at"}

CONSENT = sa.text(
    "INSERT INTO consent (sub, version, consented_at) VALUES (:sub, :version, '2026-11-13 09:30:00')"
)


@pytest.fixture(params=["sqlite", "postgresql"])
def database_url(request, tmp_path: Path) -> str:
    return database_url_for(request.param, tmp_path / "analytics.db")


def _columns(engine: sa.Engine) -> dict[str, dict]:
    return {c["name"]: c for c in sa.inspect(engine).get_columns("consent")}


def _rows(engine: sa.Engine, sql: str) -> set[tuple]:
    """값은 문자열로 맞춘다 (SQLite는 시각을 문자열로, PostgreSQL은 datetime으로 돌려준다)"""
    with engine.connect() as connection:
        return {tuple(None if v is None else str(v) for v in row) for row in connection.execute(sa.text(sql))}


def test_upgrade_adds_nullable_columns_and_downgrade_drops_them(database_url, monkeypatch) -> None:
    with migration_database(monkeypatch, database_url) as (engine, config):
        command.stamp(config, "head")
        command.downgrade(config, PREVIOUS_REVISION)
        assert not ANALYTICS_COLUMNS & set(_columns(engine))
        with engine.begin() as connection:
            connection.execute(CONSENT, {"sub": "a", "version": "2026-11-13"})
            connection.execute(CONSENT, {"sub": "a", "version": "2026-01-01"})

        command.upgrade(config, ANALYTICS_REVISION)

        columns = _columns(engine)
        assert ANALYTICS_COLUMNS <= set(columns)
        assert all(columns[name]["nullable"] for name in ANALYTICS_COLUMNS)
        assert _rows(engine, "SELECT sub, version, consented_at, analytics, analytics_updated_at FROM consent") == {
            ("a", "2026-11-13", "2026-11-13 09:30:00", None, None),
            ("a", "2026-01-01", "2026-11-13 09:30:00", None, None),
        }

        with engine.begin() as connection:
            connection.execute(sa.text(
                "UPDATE consent SET analytics = :value, analytics_updated_at = '2026-11-18 03:00:00'"
                " WHERE version = '2026-11-13'"
            ), {"value": True})
        command.downgrade(config, PREVIOUS_REVISION)

        assert not ANALYTICS_COLUMNS & set(_columns(engine))
        assert _rows(engine, "SELECT sub, version, consented_at FROM consent") == {
            ("a", "2026-11-13", "2026-11-13 09:30:00"),
            ("a", "2026-01-01", "2026-11-13 09:30:00"),
        }
        assert sa.inspect(engine).get_pk_constraint("consent")["constrained_columns"] == ["sub", "version"]

        command.upgrade(config, "head")
        with engine.connect() as connection:
            current = MigrationContext.configure(connection).get_current_revision()
        heads = ScriptDirectory.from_config(config).get_heads()
        assert heads == [current]


def test_upgrade_skips_columns_create_all_already_made(database_url, monkeypatch) -> None:
    """모델로 만든 DB(컬럼 있음)를 이전 리비전으로 표시하고 올려도 실패하지 않는다"""
    with migration_database(monkeypatch, database_url) as (engine, config):
        command.stamp(config, PREVIOUS_REVISION)

        command.upgrade(config, "head")

        assert ANALYTICS_COLUMNS <= set(_columns(engine))


def test_migrated_columns_match_model(database_url, monkeypatch) -> None:
    """마이그레이션으로 만든 두 컬럼과 모델이 만든 두 컬럼의 타입·NULL 허용이 같다"""
    with migration_database(monkeypatch, database_url) as (engine, config):
        modeled = {name: (str(c["type"]), c["nullable"]) for name, c in _columns(engine).items()
                   if name in ANALYTICS_COLUMNS}
        command.stamp(config, "head")
        command.downgrade(config, PREVIOUS_REVISION)
        command.upgrade(config, "head")

        migrated = {name: (str(c["type"]), c["nullable"]) for name, c in _columns(engine).items()
                    if name in ANALYTICS_COLUMNS}
        assert migrated == modeled
        assert set(modeled) == ANALYTICS_COLUMNS
