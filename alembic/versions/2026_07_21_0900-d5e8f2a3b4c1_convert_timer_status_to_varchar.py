"""convert timer status to varchar

timersession.status가 유일하게 네이티브 DB enum(`timerstatus` 타입)으로
생성돼 있었다 (`sa_column` 누락 → SQLModel 자동 생성). 저장 정책 통일에
따라 VARCHAR로 전환한다 — TimerStatus는 name == value라 데이터 변환이
필요 없다. (정책: tests/models/test_enum_columns.py)

Revision ID: d5e8f2a3b4c1
Revises: c4d7e8f1a2b3
Create Date: 2026-07-21 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'd5e8f2a3b4c1'
down_revision = 'c4d7e8f1a2b3'
branch_labels = None
depends_on = None

# TimerStatus.value 최대 길이 ("NOT_STARTED") — 비네이티브 Enum이 렌더링하는 VARCHAR 길이와 일치
_VARCHAR_LENGTH = 11


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLite 등은 네이티브 enum 타입이 없어 이미 TEXT로 저장됨 — 변경 불필요
        return

    op.alter_column(
        "timersession",
        "status",
        type_=sa.String(length=_VARCHAR_LENGTH),
        existing_nullable=False,
        postgresql_using="status::text",
    )
    op.execute("DROP TYPE IF EXISTS timerstatus")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        "CREATE TYPE timerstatus AS ENUM "
        "('NOT_STARTED', 'RUNNING', 'PAUSED', 'COMPLETED', 'CANCELLED')"
    )
    op.alter_column(
        "timersession",
        "status",
        type_=sa.dialects.postgresql.ENUM(name="timerstatus", create_type=False),
        existing_nullable=False,
        postgresql_using="status::timerstatus",
    )
