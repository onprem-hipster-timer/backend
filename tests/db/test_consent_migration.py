"""동의 기록을 consent 테이블로 옮기는 마이그레이션

alembic/versions/2026_11_16_1200-b3e7c1d9f4a2_move_consent_to_consent_table.py
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
from app.models.consent import Consent
from tests.db.conftest import database_url_for, migration_database

BEFORE_CONSENT_TABLE = "f2b6d8a4c3e7"
CONSENT_COLUMNS = {"consent_version", "consented_at"}

PROFILE = sa.text(
    "INSERT INTO user_profile (sub, friend_code, created_at, updated_at)"
    " VALUES (:sub, :sub, '2026-11-01 00:00:00', '2026-11-01 00:00:00')"
)
LEGACY_PROFILE = sa.text(
    "INSERT INTO user_profile (sub, friend_code, consent_version, consented_at, created_at, updated_at)"
    " VALUES (:sub, :sub, :version, :at, '2026-11-01 00:00:00', '2026-11-01 00:00:00')"
)
CONSENT = sa.text("INSERT INTO consent (sub, version, consented_at) VALUES (:sub, :version, :at)")


@pytest.fixture(params=["sqlite", "postgresql"])
def database_url(request, tmp_path: Path) -> str:
    return database_url_for(request.param, tmp_path / "consent.db")


@pytest.fixture
def legacy(database_url: str, monkeypatch: pytest.MonkeyPatch):
    """동의 기록이 user_profile 컬럼이던 리비전까지 내린 DB"""
    with migration_database(monkeypatch, database_url) as (engine, config):
        command.stamp(config, "head")
        command.downgrade(config, BEFORE_CONSENT_TABLE)
        yield engine, config


@pytest.fixture
def current(database_url: str, monkeypatch: pytest.MonkeyPatch):
    """head까지 올린 DB"""
    with migration_database(monkeypatch, database_url) as (engine, config):
        command.stamp(config, "head")
        yield engine, config


def _profile_columns(engine: sa.Engine) -> set[str]:
    return {c["name"] for c in sa.inspect(engine).get_columns("user_profile")}


def _tables(engine: sa.Engine) -> set[str]:
    return set(sa.inspect(engine).get_table_names())


def _rows(engine: sa.Engine, sql: str) -> set[tuple]:
    """값은 문자열로 맞춘다 (SQLite는 시각을 문자열로, PostgreSQL은 datetime으로 돌려준다)"""
    with engine.connect() as connection:
        return {
            tuple(None if v is None else str(v) for v in row)
            for row in connection.execute(sa.text(sql))
        }


def test_upgrade_copies_profile_consent_and_drops_columns(legacy) -> None:
    engine, config = legacy
    assert CONSENT_COLUMNS <= _profile_columns(engine)
    assert "consent" not in _tables(engine)
    with engine.begin() as connection:
        connection.execute(LEGACY_PROFILE, {"sub": "agreed", "version": "2026-11-13", "at": "2026-11-13 09:30:00"})
        connection.execute(LEGACY_PROFILE, {"sub": "old", "version": "2026-01-01", "at": "2026-01-02 00:00:00"})
        connection.execute(LEGACY_PROFILE, {"sub": "never", "version": None, "at": None})

    command.upgrade(config, "head")

    assert not CONSENT_COLUMNS & _profile_columns(engine)
    assert _rows(engine, "SELECT sub, version, consented_at FROM consent") == {
        ("agreed", "2026-11-13", "2026-11-13 09:30:00"),
        ("old", "2026-01-01", "2026-01-02 00:00:00"),
    }
    assert _rows(engine, "SELECT sub FROM user_profile") == {("agreed",), ("old",), ("never",)}


def test_upgrade_keeps_rows_that_create_all_table_already_has(legacy) -> None:
    """앱 시작의 create_all이 consent를 먼저 만들고 같은 동의를 기록했어도 실패하지 않고 한 행만 남는다"""
    engine, config = legacy
    Consent.__table__.create(engine)
    with engine.begin() as connection:
        connection.execute(LEGACY_PROFILE, {"sub": "a", "version": "2026-11-13", "at": "2026-11-13 09:30:00"})
        connection.execute(CONSENT, {"sub": "a", "version": "2026-11-13", "at": "2026-11-14 00:00:00"})
        connection.execute(CONSENT, {"sub": "guest", "version": "2026-11-13", "at": "2026-11-14 00:00:00"})

    command.upgrade(config, "head")

    assert _rows(engine, "SELECT sub, version, consented_at FROM consent") == {
        ("a", "2026-11-13", "2026-11-14 00:00:00"),
        ("guest", "2026-11-13", "2026-11-14 00:00:00"),
    }


def test_upgrade_skips_what_create_all_already_made(database_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """모델로 만든 DB(consent 있음, user_profile에 동의 컬럼 없음)에서 마이그레이션이 실패하지 않는다"""
    with migration_database(monkeypatch, database_url) as (engine, config):
        command.stamp(config, BEFORE_CONSENT_TABLE)

        command.upgrade(config, "head")

        assert "consent" in _tables(engine)
        assert not CONSENT_COLUMNS & _profile_columns(engine)


def test_downgrade_restores_each_profiles_latest_consent(current) -> None:
    engine, config = current
    with engine.begin() as connection:
        for sub in ("both", "one", "none"):
            connection.execute(PROFILE, {"sub": sub})
        connection.execute(CONSENT, {"sub": "both", "version": "2026-01-01", "at": "2026-01-02 00:00:00"})
        connection.execute(CONSENT, {"sub": "both", "version": "2026-11-13", "at": "2026-11-13 09:30:00"})
        connection.execute(CONSENT, {"sub": "one", "version": "2026-11-13", "at": "2026-11-14 00:00:00"})
        connection.execute(CONSENT, {"sub": "guest", "version": "2026-11-13", "at": "2026-11-14 00:00:00"})

    command.downgrade(config, BEFORE_CONSENT_TABLE)

    assert "consent" not in _tables(engine)
    assert _rows(engine, "SELECT sub, consent_version, consented_at FROM user_profile") == {
        ("both", "2026-11-13", "2026-11-13 09:30:00"),
        ("one", "2026-11-13", "2026-11-14 00:00:00"),
        ("none", None, None),
    }


def test_round_trip_keeps_consent_and_reaches_single_head(legacy) -> None:
    engine, config = legacy
    with engine.begin() as connection:
        connection.execute(LEGACY_PROFILE, {"sub": "a", "version": "2026-11-13", "at": "2026-11-13 09:30:00"})

    command.upgrade(config, "head")
    command.downgrade(config, BEFORE_CONSENT_TABLE)
    assert _rows(engine, "SELECT sub, consent_version, consented_at FROM user_profile") == {
        ("a", "2026-11-13", "2026-11-13 09:30:00"),
    }
    command.upgrade(config, "head")
    assert _rows(engine, "SELECT sub, version, consented_at FROM consent") == {
        ("a", "2026-11-13", "2026-11-13 09:30:00"),
    }

    with engine.connect() as connection:
        current_revision = MigrationContext.configure(connection).get_current_revision()
    heads = ScriptDirectory.from_config(config).get_heads()
    assert len(heads) == 1
    assert current_revision == heads[0]


def test_one_row_per_sub_and_version(legacy) -> None:
    engine, config = legacy
    command.upgrade(config, "head")
    with engine.begin() as connection:
        connection.execute(CONSENT, {"sub": "a", "version": "v1", "at": "2026-11-14 00:00:00"})
        connection.execute(CONSENT, {"sub": "a", "version": "v2", "at": "2026-11-14 00:00:00"})
        connection.execute(CONSENT, {"sub": "b", "version": "v1", "at": "2026-11-14 00:00:00"})
    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as connection:
            connection.execute(CONSENT, {"sub": "a", "version": "v1", "at": "2026-11-15 00:00:00"})


def _shape(engine: sa.Engine, table: str) -> tuple:
    """컬럼(타입·NULL 허용), 인덱스(이름·컬럼·unique), 기본키"""
    inspector = sa.inspect(engine)
    columns = {c["name"]: (str(c["type"]), c["nullable"]) for c in inspector.get_columns(table)}
    indexes = {
        (i["name"], tuple(i["column_names"]), bool(i["unique"]))
        for i in inspector.get_indexes(table)
        if not i.get("duplicates_constraint")
    }
    return columns, indexes, tuple(inspector.get_pk_constraint(table)["constrained_columns"])


def test_migrated_schema_matches_model(legacy, tmp_path: Path) -> None:
    """마이그레이션으로 만든 consent·user_profile과 모델이 만든 것이 같다"""
    migrated, config = legacy
    command.upgrade(config, "head")
    modeled = sa.create_engine(f"sqlite:///{(tmp_path / 'modeled.db').resolve().as_posix()}")
    SQLModel.metadata.create_all(modeled)

    for table in ("consent", "user_profile"):
        if migrated.dialect.name == "sqlite":
            assert _shape(migrated, table) == _shape(modeled, table)
        else:
            # 컬럼 타입 이름은 방언마다 달라 컬럼 이름·인덱스·기본키만 비교한다
            assert set(_shape(migrated, table)[0]) == set(_shape(modeled, table)[0])
            assert _shape(migrated, table)[1:] == _shape(modeled, table)[1:]
    modeled.dispose()
