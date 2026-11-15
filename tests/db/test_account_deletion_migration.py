"""user_profile.deletion_requested_at과 account_deletion 테이블을 더하는 마이그레이션

alembic/versions/2026_11_11_1500-b8d2f4a6c1e3_add_account_deletion.py
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlmodel import SQLModel

import app.models  # noqa: F401  # register every table in SQLModel.metadata
import app.models.holiday  # noqa: F401

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PREVIOUS_REVISION = "a7c3e9f1b2d4"


def _alembic_config(monkeypatch: pytest.MonkeyPatch, database_url: str) -> Config:
    import app.core.config as app_config
    monkeypatch.setattr(app_config.settings, "DATABASE_URL", database_url)

    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", (PROJECT_ROOT / "alembic").resolve().as_posix())
    return config


def _tables(engine: sa.Engine) -> set[str]:
    return set(sa.inspect(engine).get_table_names())


def _columns(engine: sa.Engine, table: str) -> dict[str, dict]:
    return {c["name"]: c for c in sa.inspect(engine).get_columns(table)}


def test_existing_profiles_are_not_pending_deletion_after_upgrade(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = f"sqlite:///{(tmp_path / 'deletion.db').resolve().as_posix()}"
    config = _alembic_config(monkeypatch, database_url)
    engine = sa.create_engine(database_url)
    SQLModel.metadata.create_all(engine)
    command.stamp(config, "head")
    command.downgrade(config, PREVIOUS_REVISION)

    assert "deletion_requested_at" not in _columns(engine, "user_profile")
    assert "account_deletion" not in _tables(engine)
    with engine.begin() as connection:
        connection.execute(sa.text(
            "INSERT INTO user_profile (sub, friend_code, created_at, updated_at)"
            " VALUES ('existing', 'code', '2026-11-01 00:00:00', '2026-11-01 00:00:00')"
        ))

    command.upgrade(config, "head")

    assert _columns(engine, "user_profile")["deletion_requested_at"]["nullable"]
    assert "account_deletion" in _tables(engine)
    with engine.connect() as connection:
        row = connection.execute(sa.text(
            "SELECT sub, deletion_requested_at FROM user_profile"
        )).one()
    assert tuple(row) == ("existing", None)

    command.downgrade(config, PREVIOUS_REVISION)
    assert "deletion_requested_at" not in _columns(engine, "user_profile")
    assert "account_deletion" not in _tables(engine)
    with engine.connect() as connection:
        assert connection.execute(sa.text("SELECT sub FROM user_profile")).scalar_one() == "existing"

    command.upgrade(config, "head")
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    engine.dispose()
    heads = ScriptDirectory.from_config(config).get_heads()
    assert len(heads) == 1
    assert current == heads[0]


def test_migrated_schema_matches_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """마이그레이션으로 만든 user_profile·account_deletion과 모델이 만든 것의 컬럼·인덱스가 같다"""
    migrated_url = f"sqlite:///{(tmp_path / 'migrated.db').resolve().as_posix()}"
    config = _alembic_config(monkeypatch, migrated_url)
    migrated = sa.create_engine(migrated_url)
    SQLModel.metadata.create_all(migrated)
    command.stamp(config, "head")
    command.downgrade(config, PREVIOUS_REVISION)
    command.upgrade(config, "head")

    modeled = sa.create_engine(f"sqlite:///{(tmp_path / 'modeled.db').resolve().as_posix()}")
    SQLModel.metadata.create_all(modeled)

    def shape(engine: sa.Engine, table: str) -> tuple:
        inspector = sa.inspect(engine)
        columns = {name: (str(c["type"]), c["nullable"]) for name, c in _columns(engine, table).items()}
        indexes = {(i["name"], tuple(i["column_names"]), bool(i["unique"])) for i in inspector.get_indexes(table)}
        return columns, indexes, tuple(inspector.get_pk_constraint(table)["constrained_columns"])

    for table in ("user_profile", "account_deletion"):
        assert shape(migrated, table) == shape(modeled, table), table
    migrated.dispose()
    modeled.dispose()
