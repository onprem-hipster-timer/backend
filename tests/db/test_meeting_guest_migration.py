"""미팅의 게스트 마이그레이션

alembic/versions/2026_11_17_1000-a4c8e2f6b1d3_add_allow_guests_to_meeting.py
alembic/versions/2026_11_17_1010-b5d9f3a7c2e4_add_guest_id_to_meeting_participant.py
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
from tests.db.conftest import database_url_for, migration_database

BEFORE_ALLOW_GUESTS = "73e8f92c2d27"
ALLOW_GUESTS = "a4c8e2f6b1d3"
GUEST_ID = "b5d9f3a7c2e4"

_INSERT_MEETING = sa.text(
    "INSERT INTO meeting (id, owner_id, title, start_date, end_date, timezone, available_days,"
    " start_time, end_time, time_slot_minutes, created_at, updated_at)"
    " VALUES (:id, 'owner', 'm', '2024-02-05', '2024-02-09', 'UTC', '[0]', '09:00:00', '18:00:00', 30,"
    " '2026-11-17 00:00:00', '2026-11-17 00:00:00')"
)


@pytest.fixture(params=["sqlite", "postgresql"])
def database_url(request, tmp_path: Path) -> str:
    return database_url_for(request.param, tmp_path / "meeting_guest.db")


@pytest.fixture
def engine_and_config(database_url: str, monkeypatch: pytest.MonkeyPatch):
    with migration_database(monkeypatch, database_url) as engine_and_config:
        yield engine_and_config


def _columns(engine: sa.Engine, table: str) -> dict[str, dict]:
    return {c["name"]: c for c in sa.inspect(engine).get_columns(table)}


def _single_head(engine: sa.Engine, config) -> None:
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    heads = ScriptDirectory.from_config(config).get_heads()
    assert len(heads) == 1
    assert current == heads[0]


def test_existing_meetings_get_false_and_downgrade_drops_column(engine_and_config) -> None:
    engine, config = engine_and_config
    command.stamp(config, "head")
    command.downgrade(config, BEFORE_ALLOW_GUESTS)
    assert "allow_guests" not in _columns(engine, "meeting")
    with engine.begin() as connection:
        connection.execute(_INSERT_MEETING, {"id": "a" * 32})

    command.upgrade(config, ALLOW_GUESTS)

    assert _columns(engine, "meeting")["allow_guests"]["nullable"] is False
    with engine.connect() as connection:
        assert connection.execute(sa.text("SELECT allow_guests FROM meeting")).scalar_one() in (False, 0)

    command.downgrade(config, BEFORE_ALLOW_GUESTS)
    assert "allow_guests" not in _columns(engine, "meeting")
    with engine.connect() as connection:
        assert connection.execute(sa.text("SELECT title FROM meeting")).scalar_one() == "m"

    command.upgrade(config, "head")
    _single_head(engine, config)


def test_upgrade_skips_column_that_create_all_already_made(engine_and_config) -> None:
    engine, config = engine_and_config
    command.stamp(config, BEFORE_ALLOW_GUESTS)

    command.upgrade(config, "head")

    assert _columns(engine, "meeting")["allow_guests"]["nullable"] is False


def test_migrated_meeting_columns_match_model(engine_and_config, tmp_path: Path) -> None:
    migrated, config = engine_and_config
    command.stamp(config, "head")
    command.downgrade(config, BEFORE_ALLOW_GUESTS)
    command.upgrade(config, "head")
    modeled = sa.create_engine(f"sqlite:///{(tmp_path / 'modeled.db').resolve().as_posix()}")
    SQLModel.metadata.create_all(modeled)

    def shape(engine: sa.Engine) -> dict[str, bool]:
        return {name: c["nullable"] for name, c in _columns(engine, "meeting").items()}

    assert shape(migrated) == shape(modeled)
    if migrated.dialect.name == "sqlite":
        assert _columns(migrated, "meeting")["allow_guests"]["default"] == _columns(modeled, "meeting")["allow_guests"]["default"]
    modeled.dispose()


# ============ meeting_participant.guest_id ============

_MEETING = "a" * 32
_GUEST = "b" * 32
_OTHER_GUEST = "c" * 32
_INSERT_GUEST = sa.text(
    "INSERT INTO guest (id, identity_id, resource_type, resource_id, name, created_at, updated_at)"
    " VALUES (:id, :identity, 'meeting', :resource, :name, '2026-11-17 00:00:00', '2026-11-17 00:00:00')"
)
_INSERT_PARTICIPANT = sa.text(
    "INSERT INTO meeting_participant (id, meeting_id, user_id, display_name, created_at, updated_at)"
    " VALUES (:id, :meeting, :user, 'p', '2026-11-17 00:00:00', '2026-11-17 00:00:00')"
)
_INSERT_GUEST_PARTICIPANT = sa.text(
    "INSERT INTO meeting_participant (id, meeting_id, user_id, guest_id, display_name, created_at, updated_at)"
    " VALUES (:id, :meeting, :user, :guest, 'p', '2026-11-17 00:00:00', '2026-11-17 00:00:00')"
)
_INSERT_SLOT = sa.text(
    "INSERT INTO meeting_time_slot (id, participant_id, start_time, end_time)"
    " VALUES (:id, :participant, '2024-02-05 09:00:00', '2024-02-05 10:00:00')"
)


def _hex(value) -> str:
    return value.hex if hasattr(value, "hex") else str(value).replace("-", "")


def _connect(engine: sa.Engine):
    """외래 키를 확인하는 연결 (SQLite는 연결마다 켠다)"""
    connection = engine.connect()
    if engine.dialect.name == "sqlite":
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    return connection


def _participant_shape(engine: sa.Engine) -> tuple:
    inspector = sa.inspect(engine)
    uniques = {(u["name"], tuple(u["column_names"])) for u in inspector.get_unique_constraints("meeting_participant")}
    foreign_keys = {
        (tuple(fk["constrained_columns"]), fk["referred_table"], (fk.get("options") or {}).get("ondelete"))
        for fk in inspector.get_foreign_keys("meeting_participant")
    }
    checks = {c["name"] for c in inspector.get_check_constraints("meeting_participant")}
    return uniques, foreign_keys, checks


@pytest.fixture
def before_guest_id(engine_and_config):
    """guest_id가 없던 리비전까지 내린 DB"""
    engine, config = engine_and_config
    command.stamp(config, "head")
    command.downgrade(config, ALLOW_GUESTS)
    assert "guest_id" not in _columns(engine, "meeting_participant")
    return engine, config


def test_existing_participants_keep_rows_with_null_guest_id(before_guest_id) -> None:
    engine, config = before_guest_id
    with engine.begin() as connection:
        connection.execute(_INSERT_MEETING, {"id": _MEETING})
        connection.execute(_INSERT_PARTICIPANT, {"id": "1" * 32, "meeting": _MEETING, "user": "u1"})
        connection.execute(_INSERT_PARTICIPANT, {"id": "2" * 32, "meeting": _MEETING, "user": None})
        connection.execute(_INSERT_SLOT, {"id": "3" * 32, "participant": "1" * 32})

    command.upgrade(config, GUEST_ID)

    with engine.connect() as connection:
        rows = {
            (_hex(pid), user, guest)
            for pid, user, guest in connection.execute(
                sa.text("SELECT id, user_id, guest_id FROM meeting_participant")
            )
        }
        slots = connection.execute(sa.text("SELECT count(*) FROM meeting_time_slot")).scalar_one()
    assert rows == {("1" * 32, "u1", None), ("2" * 32, None, None)}
    assert slots == 1

    command.downgrade(config, ALLOW_GUESTS)
    assert "guest_id" not in _columns(engine, "meeting_participant")
    with engine.connect() as connection:
        assert connection.execute(sa.text("SELECT count(*) FROM meeting_participant")).scalar_one() == 2
        assert connection.execute(sa.text("SELECT count(*) FROM meeting_time_slot")).scalar_one() == 1

    command.upgrade(config, "head")
    _single_head(engine, config)


def test_upgraded_constraints(before_guest_id) -> None:
    """게스트당 참여자 하나, user_id와 guest_id는 함께 둘 수 없다, 게스트 행을 지우면 참여자와 가능 시간도 지워진다"""
    engine, config = before_guest_id
    with engine.begin() as connection:
        connection.execute(_INSERT_MEETING, {"id": _MEETING})
    command.upgrade(config, "head")
    with engine.begin() as connection:
        connection.execute(_INSERT_GUEST, {"id": _GUEST, "identity": "i1", "resource": _MEETING, "name": "민수"})
        connection.execute(_INSERT_GUEST, {"id": _OTHER_GUEST, "identity": "i2", "resource": _MEETING, "name": "지수"})
        connection.execute(_INSERT_GUEST_PARTICIPANT, {"id": "1" * 32, "meeting": _MEETING, "user": None, "guest": _GUEST})
        connection.execute(_INSERT_SLOT, {"id": "2" * 32, "participant": "1" * 32})
        connection.execute(_INSERT_PARTICIPANT, {"id": "3" * 32, "meeting": _MEETING, "user": None})

    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                _INSERT_GUEST_PARTICIPANT, {"id": "4" * 32, "meeting": _MEETING, "user": None, "guest": _GUEST},
            )
    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                _INSERT_GUEST_PARTICIPANT, {"id": "5" * 32, "meeting": _MEETING, "user": "u1", "guest": _OTHER_GUEST},
            )

    with _connect(engine) as connection:
        connection.execute(sa.text("DELETE FROM guest WHERE identity_id = 'i1'"))
        connection.commit()
        participants = {_hex(pid) for (pid,) in connection.execute(sa.text("SELECT id FROM meeting_participant"))}
        slots = connection.execute(sa.text("SELECT count(*) FROM meeting_time_slot")).scalar_one()
    assert participants == {"3" * 32}
    assert slots == 0


def test_upgrade_skips_column_that_create_all_already_made_for_participant(engine_and_config) -> None:
    engine, config = engine_and_config
    command.stamp(config, ALLOW_GUESTS)

    command.upgrade(config, "head")

    assert _columns(engine, "meeting_participant")["guest_id"]["nullable"] is True


def test_migrated_participant_constraints_match_model(before_guest_id, tmp_path: Path) -> None:
    migrated, config = before_guest_id
    command.upgrade(config, "head")
    modeled = sa.create_engine(f"sqlite:///{(tmp_path / 'modeled.db').resolve().as_posix()}")
    SQLModel.metadata.create_all(modeled)

    shape = _participant_shape(migrated)
    assert ("uq_meeting_participant_guest", ("guest_id",)) in shape[0]
    assert (("guest_id",), "guest", "CASCADE") in shape[1]
    assert "ck_meeting_participant_user_or_guest" in shape[2]
    assert shape == _participant_shape(modeled)
    modeled.dispose()
