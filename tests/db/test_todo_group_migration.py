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


# ============================================================
# 할 일을 할 일 그룹으로 옮기는 마이그레이션
# alembic/versions/2026_11_13_0310-d4a8b2c6e1f9_move_todos_to_todo_group.py
# ============================================================

BEFORE_MOVE = "c1d5e9a3f7b2"
_NOW = "2026-11-13 00:00:00"


def _legacy_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str) -> tuple[sa.Engine, Config]:
    database_url = f"sqlite:///{(tmp_path / name).resolve().as_posix()}"
    config = _alembic_config(monkeypatch, database_url)
    engine = sa.create_engine(database_url)
    SQLModel.metadata.create_all(engine)
    command.stamp(config, "head")
    command.downgrade(config, BEFORE_MOVE)
    return engine, config


def _insert_legacy_rows(engine: sa.Engine) -> dict[str, str]:
    """u1의 그룹 G1·G2와 할 일. T3는 다른 그룹(G1)의 부모를, T4는 남(u1)의 그룹 G1을 쓴다"""
    ids = {name: name * 32 for name in ("a", "b", "c", "d", "e", "f")}
    g1, g2, t1, t2, t3, t4 = (ids[k] for k in ("a", "b", "c", "d", "e", "f"))
    group = sa.text(
        "INSERT INTO tag_group (id, owner_id, name, color, created_at, updated_at)"
        " VALUES (:id, 'u1', :name, '#123456', :now, :now)"
    )
    todo = sa.text(
        "INSERT INTO todo (id, owner_id, title, tag_group_id, parent_id, status, created_at, updated_at)"
        " VALUES (:id, :owner, :title, :group, :parent, 'UNSCHEDULED', :now, :now)"
    )
    with engine.begin() as connection:
        connection.execute(group, {"id": g1, "name": "업무", "now": _NOW})
        connection.execute(group, {"id": g2, "name": "개인", "now": _NOW})
        for todo_id, owner, title, group_id, parent in (
            (t1, "u1", "부모", g1, None),
            (t2, "u1", "같은 그룹 자식", g1, t1),
            (t3, "u1", "다른 그룹 자식", g2, t1),
            (t4, "u2", "남의 그룹 할 일", g1, None),
        ):
            connection.execute(todo, {
                "id": todo_id, "owner": owner, "title": title, "group": group_id, "parent": parent, "now": _NOW,
            })
    return {"g1": g1, "g2": g2, "t1": t1, "t2": t2, "t3": t3, "t4": t4}


def _todo_rows(engine: sa.Engine, group_column: str) -> dict[str, tuple]:
    with engine.connect() as connection:
        rows = connection.execute(sa.text(f"SELECT id, {group_column}, parent_id FROM todo")).all()
    return {row[0]: (row[1], row[2]) for row in rows}


def test_upgrade_moves_todos_to_todo_groups_with_same_ids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine, config = _legacy_engine(tmp_path, monkeypatch, "move.db")
    ids = _insert_legacy_rows(engine)

    command.upgrade(config, "head")

    columns = {c["name"] for c in sa.inspect(engine).get_columns("todo")}
    assert "tag_group_id" not in columns
    with engine.connect() as connection:
        groups = {row[0]: tuple(row[1:]) for row in connection.execute(sa.text(
            "SELECT id, owner_id, name, is_default FROM todo_group"
        ))}
    todos = _todo_rows(engine, "todo_group_id")
    assert groups[ids["g1"]] == ("u1", "업무", False)
    assert groups[ids["g2"]] == ("u1", "개인", False)
    assert todos[ids["t1"]] == (ids["g1"], None)
    assert todos[ids["t2"]] == (ids["g1"], ids["t1"])
    # 부모와 그룹이 다르면 부모 연결을 끊는다
    assert todos[ids["t3"]] == (ids["g2"], None)
    # 남의 그룹에 있던 할 일은 그 사람 소유의 같은 이름 그룹으로 간다
    moved_group = todos[ids["t4"]][0]
    assert moved_group not in (ids["g1"], ids["g2"])
    assert groups[moved_group] == ("u2", "업무", False)
    engine.dispose()


def test_downgrade_restores_tag_group_ids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine, config = _legacy_engine(tmp_path, monkeypatch, "restore.db")
    ids = _insert_legacy_rows(engine)
    command.upgrade(config, "head")
    moved_group = _todo_rows(engine, "todo_group_id")[ids["t4"]][0]

    command.downgrade(config, BEFORE_MOVE)

    columns = {c["name"] for c in sa.inspect(engine).get_columns("todo")}
    assert "todo_group_id" not in columns
    todos = _todo_rows(engine, "tag_group_id")
    assert todos[ids["t1"]][0] == ids["g1"]
    assert todos[ids["t3"]][0] == ids["g2"]
    assert todos[ids["t4"]][0] == moved_group
    with engine.connect() as connection:
        owner = connection.execute(
            sa.text("SELECT owner_id FROM tag_group WHERE id = :id"), {"id": moved_group},
        ).scalar_one()
    assert owner == "u2"
    engine.dispose()


def test_migrated_todo_schema_matches_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """마이그레이션으로 만든 todo와 모델이 만든 것의 컬럼·인덱스·외래키가 같다"""
    migrated, config = _legacy_engine(tmp_path, monkeypatch, "todo_migrated.db")
    command.upgrade(config, "head")
    modeled = sa.create_engine(f"sqlite:///{(tmp_path / 'todo_modeled.db').resolve().as_posix()}")
    SQLModel.metadata.create_all(modeled)

    assert _shape(migrated, "todo") == _shape(modeled, "todo")
    migrated.dispose()
    modeled.dispose()


# ============================================================
# 일정의 tag_group_id를 지우는 마이그레이션
# alembic/versions/2026_11_13_0320-e7f3a9c5b1d8_drop_schedule_tag_group_id.py
# ============================================================

BEFORE_SCHEDULE_DROP = "d4a8b2c6e1f9"


def test_schedule_tag_group_id_round_trips(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = f"sqlite:///{(tmp_path / 'schedule.db').resolve().as_posix()}"
    config = _alembic_config(monkeypatch, database_url)
    engine = sa.create_engine(database_url)
    SQLModel.metadata.create_all(engine)
    command.stamp(config, "head")

    command.downgrade(config, BEFORE_SCHEDULE_DROP)
    assert "tag_group_id" in {c["name"] for c in sa.inspect(engine).get_columns("schedule")}

    command.upgrade(config, "head")
    assert "tag_group_id" not in {c["name"] for c in sa.inspect(engine).get_columns("schedule")}
    engine.dispose()


def test_migrated_schedule_schema_matches_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    migrated, config = _legacy_engine(tmp_path, monkeypatch, "schedule_migrated.db")
    command.upgrade(config, "head")
    modeled = sa.create_engine(f"sqlite:///{(tmp_path / 'schedule_modeled.db').resolve().as_posix()}")
    SQLModel.metadata.create_all(modeled)

    assert _shape(migrated, "schedule") == _shape(modeled, "schedule")
    migrated.dispose()
    modeled.dispose()
