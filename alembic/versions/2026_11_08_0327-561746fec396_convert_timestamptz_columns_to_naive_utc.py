"""convert timestamptz columns to naive utc

create_all로 만들어진 timestamptz 컬럼을 저장 계약인 UTC naive 컬럼으로 맞춘다.
같은 UTC 시각을 유지하며, 이미 naive인 컬럼은 건너뛴다 (PostgreSQL 전용).

회귀 테스트: tests/db/test_naive_utc_columns_migration.py

Revision ID: 561746fec396
Revises: c4d7e8f1a2b3
Create Date: 2026-11-08 03:27:02.074065+09:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '561746fec396'
down_revision: Union[str, None] = 'c4d7e8f1a2b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 이 리비전 시점 모델의 DateTime 컬럼
DATETIME_COLUMNS = {
    "friendship": ("created_at", "updated_at"),
    "meeting": ("created_at", "updated_at"),
    "meeting_participant": ("created_at", "updated_at"),
    "resource_visibility": ("created_at", "updated_at"),
    "schedule": ("created_at", "updated_at", "start_time", "end_time", "recurrence_end"),
    "scheduleexception": ("created_at", "updated_at", "exception_date", "start_time", "end_time"),
    "tag": ("created_at", "updated_at"),
    "tag_group": ("created_at", "updated_at"),
    "timersession": ("created_at", "updated_at", "started_at", "paused_at", "ended_at"),
    "todo": ("created_at", "updated_at", "deadline"),
    "user_profile": ("created_at", "updated_at"),
    "holidays": ("created_at", "updated_at", "start_date", "end_date"),
    "holiday_hashes": ("created_at", "updated_at"),
}


def _convert(*, to_timezone: bool) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    for table, columns in DATETIME_COLUMNS.items():
        if table not in existing_tables:
            continue
        reflected = {c["name"]: c["type"] for c in inspector.get_columns(table)}
        for column in columns:
            column_type = reflected.get(column)
            # 이미 목표 타입인 컬럼에 AT TIME ZONE을 걸면 값이 시차만큼 밀린다
            if not isinstance(column_type, sa.DateTime) or column_type.timezone == to_timezone:
                continue
            op.alter_column(
                table,
                column,
                type_=sa.DateTime(timezone=to_timezone),
                postgresql_using=f"{column} AT TIME ZONE 'UTC'",
            )


def upgrade() -> None:
    _convert(to_timezone=False)


def downgrade() -> None:
    _convert(to_timezone=True)
