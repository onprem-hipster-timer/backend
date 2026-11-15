"""user_profile에 동의 기록 컬럼을 더하는 마이그레이션

alembic/versions/2026_11_11_1200-a7c3e9f1b2d4_add_consent_to_user_profile.py
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
PREVIOUS_REVISION = "314620d41758"
CONSENT_COLUMNS = {"consent_version", "consented_at"}


def _alembic_config(monkeypatch: pytest.MonkeyPatch, database_url: str) -> Config:
    import app.core.config as app_config
    monkeypatch.setattr(app_config.settings, "DATABASE_URL", database_url)

    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", (PROJECT_ROOT / "alembic").resolve().as_posix())
    return config


def _columns(engine: sa.Engine) -> dict[str, dict]:
    return {c["name"]: c for c in sa.inspect(engine).get_columns("user_profile")}


def test_existing_profiles_need_consent_after_upgrade(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = f"sqlite:///{(tmp_path / 'consent.db').resolve().as_posix()}"
    config = _alembic_config(monkeypatch, database_url)
    engine = sa.create_engine(database_url)
    SQLModel.metadata.create_all(engine)
    command.stamp(config, "head")
    command.downgrade(config, PREVIOUS_REVISION)

    assert not CONSENT_COLUMNS & set(_columns(engine))
    with engine.begin() as connection:
        connection.execute(sa.text(
            "INSERT INTO user_profile (sub, friend_code, created_at, updated_at)"
            " VALUES ('existing', 'code', '2026-11-01 00:00:00', '2026-11-01 00:00:00')"
        ))

    command.upgrade(config, "head")

    columns = _columns(engine)
    assert CONSENT_COLUMNS <= set(columns)
    assert all(columns[name]["nullable"] for name in CONSENT_COLUMNS)
    with engine.connect() as connection:
        row = connection.execute(sa.text(
            "SELECT sub, consent_version, consented_at FROM user_profile"
        )).one()
    assert tuple(row) == ("existing", None, None)

    command.downgrade(config, PREVIOUS_REVISION)
    assert not CONSENT_COLUMNS & set(_columns(engine))
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
    """마이그레이션으로 만든 user_profile과 모델이 만든 user_profile의 컬럼이 같다"""
    migrated_url = f"sqlite:///{(tmp_path / 'migrated.db').resolve().as_posix()}"
    config = _alembic_config(monkeypatch, migrated_url)
    migrated = sa.create_engine(migrated_url)
    SQLModel.metadata.create_all(migrated)
    command.stamp(config, "head")
    command.downgrade(config, PREVIOUS_REVISION)
    command.upgrade(config, "head")

    modeled = sa.create_engine(f"sqlite:///{(tmp_path / 'modeled.db').resolve().as_posix()}")
    SQLModel.metadata.create_all(modeled)

    def shape(engine: sa.Engine) -> dict[str, tuple[str, bool]]:
        return {name: (str(c["type"]), c["nullable"]) for name, c in _columns(engine).items()}

    assert shape(migrated) == shape(modeled)
    migrated.dispose()
    modeled.dispose()
