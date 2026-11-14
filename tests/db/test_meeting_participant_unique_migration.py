"""미팅마다 사용자당 참여자 한 명 마이그레이션

alembic/versions/2026_11_14_0900-3f1fcd3dae5f_unique_meeting_participant_per_user.py
"""

from __future__ import annotations

import os
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
BEFORE_UNIQUE = "aeb221d93ba3"
CONSTRAINT = "uq_meeting_participant_meeting_user"
_TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")


def _alembic_config(monkeypatch: pytest.MonkeyPatch, database_url: str) -> Config:
    import app.core.config as app_config
    monkeypatch.setattr(app_config.settings, "DATABASE_URL", database_url)

    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", (PROJECT_ROOT / "alembic").resolve().as_posix())
    return config


@pytest.fixture(params=["sqlite", "postgresql"])
def database_url(request, tmp_path: Path) -> str:
    if request.param == "sqlite":
        return f"sqlite:///{(tmp_path / 'participant.db').resolve().as_posix()}"
    if not _TEST_DATABASE_URL.startswith("postgresql"):
        pytest.skip("requires PostgreSQL via TEST_DATABASE_URL")
    return _TEST_DATABASE_URL


@pytest.fixture
def legacy(database_url: str, monkeypatch: pytest.MonkeyPatch):
    """제약이 없던 리비전까지 내린 DB"""
    config = _alembic_config(monkeypatch, database_url)
    engine = sa.create_engine(database_url)
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    command.stamp(config, "head")
    command.downgrade(config, BEFORE_UNIQUE)
    yield engine, config
    SQLModel.metadata.drop_all(engine)
    with engine.begin() as connection:
        connection.execute(sa.text("DROP TABLE IF EXISTS alembic_version"))
    engine.dispose()


def _unique_constraints(engine: sa.Engine) -> set[tuple[str, tuple[str, ...]]]:
    return {
        (u["name"], tuple(u["column_names"]))
        for u in sa.inspect(engine).get_unique_constraints("meeting_participant")
    }


def _shape(engine: sa.Engine, table: str) -> tuple:
    """컬럼(타입·NULL 허용), 인덱스(이름·컬럼·unique), unique 제약, 외래키(컬럼·참조·ondelete), 기본키"""
    inspector = sa.inspect(engine)
    columns = {c["name"]: (str(c["type"]), c["nullable"]) for c in inspector.get_columns(table)}
    # PostgreSQL은 unique 제약을 같은 이름의 unique 인덱스로도 돌려주므로 인덱스에서는 뺀다
    indexes = {
        (i["name"], tuple(i["column_names"]), bool(i["unique"]))
        for i in inspector.get_indexes(table)
        if not i.get("duplicates_constraint")
    }
    uniques = {(u["name"], tuple(u["column_names"])) for u in inspector.get_unique_constraints(table)}
    foreign_keys = {
        (tuple(fk["constrained_columns"]), fk["referred_table"], (fk.get("options") or {}).get("ondelete"))
        for fk in inspector.get_foreign_keys(table)
    }
    return columns, indexes, uniques, foreign_keys, tuple(inspector.get_pk_constraint(table)["constrained_columns"])


_MEETING_A = "a" * 32
_MEETING_B = "b" * 32


def _insert_rows(engine: sa.Engine) -> None:
    """u1은 미팅 A에 세 번(1·2·3), 미팅 B에 한 번(4), u2는 A에 한 번(5), 로그인하지 않은 참여자 둘(6·7)"""
    meeting = sa.text(
        "INSERT INTO meeting (id, owner_id, title, start_date, end_date, available_days,"
        " start_time, end_time, time_slot_minutes, created_at, updated_at)"
        " VALUES (:id, 'owner', 'm', '2024-02-05', '2024-02-09', '[0]', '09:00:00', '18:00:00', 30,"
        " '2026-11-14 00:00:00', '2026-11-14 00:00:00')"
    )
    participant = sa.text(
        "INSERT INTO meeting_participant (id, meeting_id, user_id, display_name, created_at, updated_at)"
        " VALUES (:id, :meeting, :user, :name, :created, :created)"
    )
    slot = sa.text(
        "INSERT INTO meeting_time_slot (id, participant_id, slot_date, start_time, end_time)"
        " VALUES (:id, :participant, '2024-02-05', '09:00:00', '10:00:00')"
    )
    with engine.begin() as connection:
        connection.execute(meeting, {"id": _MEETING_A})
        connection.execute(meeting, {"id": _MEETING_B})
        for n, meeting_id, user, created in (
            (1, _MEETING_A, "u1", "2026-11-14 01:00:00"),
            (2, _MEETING_A, "u1", "2026-11-14 03:00:00"),
            (3, _MEETING_A, "u1", "2026-11-14 02:00:00"),
            (4, _MEETING_B, "u1", "2026-11-14 01:00:00"),
            (5, _MEETING_A, "u2", "2026-11-14 01:00:00"),
            (6, _MEETING_A, None, "2026-11-14 01:00:00"),
            (7, _MEETING_A, None, "2026-11-14 02:00:00"),
        ):
            connection.execute(participant, {
                "id": f"{n:032x}", "meeting": meeting_id, "user": user, "name": f"p{n}", "created": created,
            })
            connection.execute(slot, {"id": f"{100 + n:032x}", "participant": f"{n:032x}"})


def _rows(engine: sa.Engine, sql: str) -> set:
    with engine.connect() as connection:
        return {tuple(row) for row in connection.execute(sa.text(sql))}


def _hex(value) -> str:
    return value.hex if hasattr(value, "hex") else str(value).replace("-", "")


def test_upgrade_keeps_latest_participant_per_user_and_adds_constraint(legacy) -> None:
    engine, config = legacy
    _insert_rows(engine)

    command.upgrade(config, "head")

    participants = {
        (_hex(pid), name) for pid, name in _rows(engine, "SELECT id, display_name FROM meeting_participant")
    }
    assert participants == {
        (f"{2:032x}", "p2"),  # u1의 미팅 A 참여 중 가장 나중에 만든 것
        (f"{4:032x}", "p4"),
        (f"{5:032x}", "p5"),
        (f"{6:032x}", "p6"),
        (f"{7:032x}", "p7"),
    }
    slots = {
        (_hex(sid), _hex(pid))
        for sid, pid in _rows(engine, "SELECT id, participant_id FROM meeting_time_slot")
    }
    # 지운 참여자의 가능 시간은 함께 지우고, 남은 참여자의 가능 시간은 그대로 둔다
    assert slots == {(f"{100 + n:032x}", f"{n:032x}") for n in (2, 4, 5, 6, 7)}
    assert (CONSTRAINT, ("meeting_id", "user_id")) in _unique_constraints(engine)


def test_constraint_allows_one_participant_per_user_and_any_number_without_user(legacy) -> None:
    engine, config = legacy
    command.upgrade(config, "head")
    _insert_rows_after = sa.text(
        "INSERT INTO meeting_participant (id, meeting_id, user_id, display_name, created_at, updated_at)"
        " VALUES (:id, :meeting, :user, 'p', '2026-11-14 00:00:00', '2026-11-14 00:00:00')"
    )
    with engine.begin() as connection:
        connection.execute(sa.text(
            "INSERT INTO meeting (id, owner_id, title, start_date, end_date, available_days,"
            " start_time, end_time, time_slot_minutes, created_at, updated_at)"
            " VALUES (:id, 'owner', 'm', '2024-02-05', '2024-02-09', '[0]', '09:00:00', '18:00:00', 30,"
            " '2026-11-14 00:00:00', '2026-11-14 00:00:00')"
        ), {"id": _MEETING_A})
        connection.execute(_insert_rows_after, {"id": "1" * 32, "meeting": _MEETING_A, "user": "u1"})
        connection.execute(_insert_rows_after, {"id": "2" * 32, "meeting": _MEETING_A, "user": None})
        connection.execute(_insert_rows_after, {"id": "3" * 32, "meeting": _MEETING_A, "user": None})
    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as connection:
            connection.execute(_insert_rows_after, {"id": "4" * 32, "meeting": _MEETING_A, "user": "u1"})


def test_round_trip_reaches_single_head(legacy) -> None:
    engine, config = legacy
    assert CONSTRAINT not in {name for name, _ in _unique_constraints(engine)}

    command.upgrade(config, "head")
    assert CONSTRAINT in {name for name, _ in _unique_constraints(engine)}
    command.downgrade(config, BEFORE_UNIQUE)
    assert CONSTRAINT not in {name for name, _ in _unique_constraints(engine)}
    command.upgrade(config, "head")

    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    heads = ScriptDirectory.from_config(config).get_heads()
    assert len(heads) == 1
    assert current == heads[0]


def test_upgrade_skips_constraint_that_create_all_already_made(
        database_url: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """앱 시작의 create_all이 제약을 먼저 만들었어도 마이그레이션이 실패하지 않는다"""
    config = _alembic_config(monkeypatch, database_url)
    engine = sa.create_engine(database_url)
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    command.stamp(config, BEFORE_UNIQUE)
    try:
        command.upgrade(config, "head")

        assert (CONSTRAINT, ("meeting_id", "user_id")) in _unique_constraints(engine)
    finally:
        SQLModel.metadata.drop_all(engine)
        with engine.begin() as connection:
            connection.execute(sa.text("DROP TABLE IF EXISTS alembic_version"))
        engine.dispose()


def test_migrated_schema_matches_model(legacy, tmp_path: Path) -> None:
    """마이그레이션으로 만든 meeting_participant·meeting_time_slot과 모델이 만든 것이 같다"""
    migrated, config = legacy
    command.upgrade(config, "head")
    modeled = sa.create_engine(f"sqlite:///{(tmp_path / 'modeled.db').resolve().as_posix()}")
    SQLModel.metadata.create_all(modeled)

    for table in ("meeting_participant", "meeting_time_slot"):
        if migrated.dialect.name == "sqlite":
            assert _shape(migrated, table) == _shape(modeled, table)
        else:
            # 컬럼 타입 이름은 방언마다 달라 인덱스·unique 제약·외래키·기본키만 비교한다
            assert _shape(migrated, table)[1:] == _shape(modeled, table)[1:]
    modeled.dispose()
