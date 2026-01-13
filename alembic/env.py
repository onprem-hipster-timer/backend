"""
Alembic 마이그레이션 환경 설정

Best Practices:
1. SQLModel 메타데이터 사용
2. 환경 변수/설정에서 DB URL 가져오기
3. 모든 모델 자동 import로 autogenerate 지원
"""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ============================================================
# 모든 모델 Import (autogenerate가 변경사항 감지하려면 필수)
# ============================================================
# SQLModel의 메타데이터에 모든 테이블 등록을 위해 모델 import
from app.models import (  # noqa: E402, F401
    Schedule,
    ScheduleException,
    TimerSession,
    TagGroup,
    Tag,
    ScheduleTag,
    ScheduleExceptionTag,
    TodoTag,
    Todo,
)
from app.models.tag import TimerTag  # noqa: E402, F401
from app.domain.holiday.model import HolidayModel, HolidayHashModel  # noqa: E402, F401

# SQLModel 메타데이터 사용 (autogenerate 지원)
target_metadata = SQLModel.metadata

# ============================================================
# 설정에서 DB URL 가져오기
# ============================================================
from app.core.config import settings  # noqa: E402

# alembic.ini의 sqlalchemy.url을 덮어쓰기
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)


def _is_sqlite() -> bool:
    """SQLite 데이터베이스 여부 확인"""
    return settings.DATABASE_URL.startswith("sqlite")


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well. By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # SQLite만 batch mode 필요 (ALTER TABLE 제한 우회)
        render_as_batch=_is_sqlite(),
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite만 batch mode 필요 (ALTER TABLE 제한 우회)
            render_as_batch=_is_sqlite(),
            # 타입 변경 감지 (기본값 False)
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
