"""할 일 그룹 마이그레이션

alembic/versions/2026_11_13_0300-c1d5e9a3f7b2_add_todo_group.py
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
BEFORE_TODO_GROUP = "b8d2f4a6c1e3"


def _alembic_config(monkeypatch: pytest.MonkeyPatch, database_url: str) -> Config:
    import app.core.config as app_config
    monkeypatch.setattr(app_config.settings, "DATABASE_URL", database_url)

    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", (PROJECT_ROOT / "alembic").resolve().as_posix())
    return config


def _tables(engine: sa.Engine) -> set[str]:
    return set(sa.inspect(engine).get_table_names())


def _shape(engine: sa.Engine, table: str) -> tuple:
    """컬럼(타입·NULL 허용), 인덱스(이름·컬럼·unique), 외래키(컬럼·참조·ondelete), 기본키"""
    inspector = sa.inspect(engine)
    columns = {c["name"]: (str(c["type"]), c["nullable"]) for c in inspector.get_columns(table)}
    indexes = {(i["name"], tuple(i["column_names"]), bool(i["unique"])) for i in inspector.get_indexes(table)}
    foreign_keys = {
        (tuple(fk["constrained_columns"]), fk["referred_table"], (fk.get("options") or {}).get("ondelete"))
        for fk in inspector.get_foreign_keys(table)
    }
    return columns, indexes, foreign_keys, tuple(inspector.get_pk_constraint(table)["constrained_columns"])


def test_todo_group_table_round_trips(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = f"sqlite:///{(tmp_path / 'todo_group.db').resolve().as_posix()}"
    config = _alembic_config(monkeypatch, database_url)
    engine = sa.create_engine(database_url)
    SQLModel.metadata.create_all(engine)
    command.stamp(config, "head")

    command.downgrade(config, BEFORE_TODO_GROUP)
    assert "todo_group" not in _tables(engine)

    command.upgrade(config, "head")
    assert "todo_group" in _tables(engine)

    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    engine.dispose()
    heads = ScriptDirectory.from_config(config).get_heads()
    assert len(heads) == 1
    assert current == heads[0]


def test_upgrade_skips_table_that_create_all_already_made(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """앱 시작의 create_all이 todo_group을 먼저 만들었어도 마이그레이션이 실패하지 않는다"""
    database_url = f"sqlite:///{(tmp_path / 'created.db').resolve().as_posix()}"
    config = _alembic_config(monkeypatch, database_url)
    engine = sa.create_engine(database_url)
    SQLModel.metadata.create_all(engine)
    command.stamp(config, BEFORE_TODO_GROUP)

    command.upgrade(config, "head")

    assert "todo_group" in _tables(engine)
    engine.dispose()


def test_only_one_default_group_per_owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """마이그레이션이 만든 부분 unique 인덱스가 사용자당 기본 그룹을 하나로 막고, 일반 그룹은 막지 않는다"""
    database_url = f"sqlite:///{(tmp_path / 'default.db').resolve().as_posix()}"
    config = _alembic_config(monkeypatch, database_url)
    engine = sa.create_engine(database_url)
    SQLModel.metadata.create_all(engine)
    command.stamp(config, "head")
    command.downgrade(config, BEFORE_TODO_GROUP)
    command.upgrade(config, "head")

    insert = sa.text(
        "INSERT INTO todo_group (id, owner_id, name, color, is_default, created_at, updated_at)"
        " VALUES (:id, :owner, 'g', '#2196F3', :is_default, '2026-11-13 00:00:00', '2026-11-13 00:00:00')"
    )
    with engine.begin() as connection:
        connection.execute(insert, {"id": "a" * 32, "owner": "u1", "is_default": True})
        connection.execute(insert, {"id": "b" * 32, "owner": "u1", "is_default": False})
        connection.execute(insert, {"id": "c" * 32, "owner": "u1", "is_default": False})
        connection.execute(insert, {"id": "d" * 32, "owner": "u2", "is_default": True})
    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as connection:
            connection.execute(insert, {"id": "e" * 32, "owner": "u1", "is_default": True})
    engine.dispose()


def test_migrated_schema_matches_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """마이그레이션으로 만든 todo_group과 모델이 만든 것의 컬럼·인덱스·외래키가 같다"""
    migrated_url = f"sqlite:///{(tmp_path / 'migrated.db').resolve().as_posix()}"
    config = _alembic_config(monkeypatch, migrated_url)
    migrated = sa.create_engine(migrated_url)
    SQLModel.metadata.create_all(migrated)
    command.stamp(config, "head")
    command.downgrade(config, BEFORE_TODO_GROUP)
    command.upgrade(config, "head")

    modeled = sa.create_engine(f"sqlite:///{(tmp_path / 'modeled.db').resolve().as_posix()}")
    SQLModel.metadata.create_all(modeled)

    assert _shape(migrated, "todo_group") == _shape(modeled, "todo_group")
    migrated.dispose()
    modeled.dispose()
