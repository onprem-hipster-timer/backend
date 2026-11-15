"""tests/db 마이그레이션 테스트가 함께 쓰는 DB 준비"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlmodel import SQLModel

import app.models  # noqa: F401  # register every table in SQLModel.metadata
import app.models.holiday  # noqa: F401

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")


def database_url_for(dialect: str, sqlite_file: Path) -> str:
    """sqlite면 sqlite_file, postgresql이면 TEST_DATABASE_URL (PostgreSQL이 아니면 건너뛴다)"""
    if dialect == "sqlite":
        return f"sqlite:///{sqlite_file.resolve().as_posix()}"
    if not _TEST_DATABASE_URL.startswith("postgresql"):
        pytest.skip("requires PostgreSQL via TEST_DATABASE_URL")
    return _TEST_DATABASE_URL


@contextmanager
def migration_database(monkeypatch: pytest.MonkeyPatch, database_url: str) -> Iterator[tuple[sa.Engine, Config]]:
    """모델로 테이블을 새로 만든 DB와 그 DB를 보는 alembic 설정. 끝나면 테이블과 alembic_version을 지운다"""
    # alembic env.py는 실행 시점의 settings.DATABASE_URL을 읽는다
    import app.core.config as app_config
    monkeypatch.setattr(app_config.settings, "DATABASE_URL", database_url)
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", (PROJECT_ROOT / "alembic").resolve().as_posix())

    engine = sa.create_engine(database_url)
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    try:
        yield engine, config
    finally:
        SQLModel.metadata.drop_all(engine)
        with engine.begin() as connection:
            connection.execute(sa.text("DROP TABLE IF EXISTS alembic_version"))
        engine.dispose()
