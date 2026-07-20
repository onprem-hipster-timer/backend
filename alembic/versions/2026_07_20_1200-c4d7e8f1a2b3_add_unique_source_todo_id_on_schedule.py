"""add unique source_todo_id on schedule

'할일당 투영 일정은 정확히 1개' 불변조건을 DB가 최종 보장한다
(partial unique index — source_todo_id가 NULL이 아닌 행에만 적용).

Revision ID: c4d7e8f1a2b3
Revises: b9e4d2a1c3f5
Create Date: 2026-07-20 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c4d7e8f1a2b3'
down_revision = 'b9e4d2a1c3f5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_schedule_source_todo_id",
        "schedule",
        ["source_todo_id"],
        unique=True,
        postgresql_where=sa.text("source_todo_id IS NOT NULL"),
        sqlite_where=sa.text("source_todo_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_schedule_source_todo_id", table_name="schedule")
