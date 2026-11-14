"""게스트 마이그레이션

alembic/versions/2026_11_14_1200-f2b6d8a4c3e7_add_guest.py
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
BEFORE_GUEST = "e7f3a9c5b1d8"
INSERT = sa.text(
    "INSERT INTO guest (id, identity_id, resource_type, resource_id, name, created_at, updated_at)"
    " VALUES (:id, :identity, :resource_type, :resource, :name, '2026-11-14 00:00:00', '2026-11-14 00:00:00')"
).bindparams(resource_type="meeting")


def _alembic_config(monkeypatch: pytest.MonkeyPatch, database_url: str) -> Config:
    import app.core.config as app_config
    monkeypatch.setattr(app_config.settings, "DATABASE_URL", database_url)

    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", (PROJECT_ROOT / "alembic").resolve().as_posix())
    return config


def _database_url(tmp_path: Path, name: str) -> str:
    """TEST_DATABASE_URL이 PostgreSQL이면 그 DB, 아니면 tmp_path의 SQLite 파일"""
    import os

    url = os.environ.get("TEST_DATABASE_URL", "")
    if url.startswith("postgresql"):
        return url
    return f"sqlite:///{(tmp_path / name).resolve().as_posix()}"


def _tables(engine: sa.Engine) -> set[str]:
    return set(sa.inspect(engine).get_table_names())


def _shape(engine: sa.Engine, table: str) -> tuple:
    """컬럼(타입·NULL 허용), 인덱스(이름·컬럼·unique), 기본키, unique 제약(이름·컬럼)"""
    inspector = sa.inspect(engine)
    columns = {c["name"]: (str(c["type"]), c["nullable"]) for c in inspector.get_columns(table)}
    # PostgreSQL은 unique 제약의 인덱스도 인덱스로 돌려준다 (duplicates_constraint). 제약은 uniques로 본다
    indexes = {
        (i["name"], tuple(i["column_names"]), bool(i["unique"]))
        for i in inspector.get_indexes(table)
        if not i.get("duplicates_constraint")
    }
    uniques = {(u["name"], tuple(u["column_names"])) for u in inspector.get_unique_constraints(table)}
    return columns, indexes, tuple(inspector.get_pk_constraint(table)["constrained_columns"]), uniques


@pytest.fixture
def migrated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """head까지 만든 DB에서 guest만 내렸다가 다시 올린 엔진과 alembic 설정"""
    database_url = _database_url(tmp_path, "guest.db")
    config = _alembic_config(monkeypatch, database_url)
    engine = sa.create_engine(database_url)
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    command.stamp(config, "head")
    yield engine, config
    with engine.begin() as connection:
        connection.execute(sa.text("DROP TABLE IF EXISTS alembic_version"))
    SQLModel.metadata.drop_all(engine)
    engine.dispose()


def test_guest_table_round_trips(migrated) -> None:
    engine, config = migrated

    command.downgrade(config, BEFORE_GUEST)
    assert "guest" not in _tables(engine)

    command.upgrade(config, "head")
    assert "guest" in _tables(engine)

    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    heads = ScriptDirectory.from_config(config).get_heads()
    assert len(heads) == 1
    assert current == heads[0]


def test_upgrade_skips_table_that_create_all_already_made(migrated) -> None:
    """앱 시작의 create_all이 guest를 먼저 만들었어도 마이그레이션이 실패하지 않는다"""
    engine, config = migrated
    command.stamp(config, BEFORE_GUEST)

    command.upgrade(config, "head")

    assert "guest" in _tables(engine)


def test_identity_id_is_unique(migrated) -> None:
    """한 Kratos identity는 게스트 행 하나에만 연결된다"""
    engine, config = migrated
    command.downgrade(config, BEFORE_GUEST)
    command.upgrade(config, "head")

    with engine.begin() as connection:
        connection.execute(INSERT, {"id": "a" * 32, "identity": "i1", "resource": "1" * 32, "name": "a"})
        connection.execute(INSERT, {"id": "b" * 32, "identity": "i2", "resource": "1" * 32, "name": "b"})
    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as connection:
            connection.execute(INSERT, {"id": "c" * 32, "identity": "i1", "resource": "2" * 32, "name": "c"})


def test_name_is_unique_within_one_resource(migrated) -> None:
    """같은 리소스(종류·id)에서 이름은 하나뿐이다. 다른 리소스나 다른 종류에서는 같은 이름을 쓸 수 있다"""
    engine, config = migrated
    command.downgrade(config, BEFORE_GUEST)
    command.upgrade(config, "head")

    with engine.begin() as connection:
        connection.execute(INSERT, {"id": "a" * 32, "identity": "i1", "resource": "1" * 32, "name": "민수"})
        connection.execute(INSERT, {"id": "b" * 32, "identity": "i2", "resource": "2" * 32, "name": "민수"})
        connection.execute(
            INSERT.bindparams(resource_type="todo"),
            {"id": "c" * 32, "identity": "i3", "resource": "1" * 32, "name": "민수"},
        )
    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as connection:
            connection.execute(INSERT, {"id": "d" * 32, "identity": "i4", "resource": "1" * 32, "name": "민수"})


def test_migrated_schema_matches_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, migrated) -> None:
    """마이그레이션으로 만든 guest와 모델이 만든 것의 컬럼·인덱스·unique 제약이 같다"""
    engine, config = migrated
    command.downgrade(config, BEFORE_GUEST)
    command.upgrade(config, "head")
    migrated_shape = _shape(engine, "guest")
    assert ("uq_guest_resource_name", ("resource_type", "resource_id", "name")) in migrated_shape[3]

    modeled = sa.create_engine(f"sqlite:///{(tmp_path / 'modeled.db').resolve().as_posix()}")
    SQLModel.metadata.create_all(modeled)
    if engine.dialect.name == "sqlite":
        assert migrated_shape == _shape(modeled, "guest")
    else:
        assert migrated_shape[1:] == _shape(modeled, "guest")[1:]
        assert set(migrated_shape[0]) == set(_shape(modeled, "guest")[0])
    modeled.dispose()
