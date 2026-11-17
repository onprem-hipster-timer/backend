"""add kind to meeting_time_slot

meeting_time_slot에 구간의 종류(kind: available, unavailable, 서버 기본값 available)를 더한다. 기존 행은 available이다.
앱 시작의 create_all이 컬럼을 먼저 만들었으면 건너뛴다.
downgrade는 unavailable 구간을 지운 뒤 컬럼을 없앤다.

회귀 테스트: tests/db/test_meeting_time_slot_kind_migration.py

Revision ID: 9d3b480a27c9
Revises: 88d59fb76aa6
Create Date: 2026-11-17 11:30:00.000000+09:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9d3b480a27c9'
down_revision: Union[str, None] = '88d59fb76aa6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if 'kind' in {c['name'] for c in sa.inspect(op.get_bind()).get_columns('meeting_time_slot')}:
        return

    with op.batch_alter_table('meeting_time_slot') as batch_op:
        batch_op.add_column(sa.Column('kind', sa.String(length=11), nullable=False, server_default='available'))


def downgrade() -> None:
    op.execute("DELETE FROM meeting_time_slot WHERE kind = 'unavailable'")
    with op.batch_alter_table('meeting_time_slot') as batch_op:
        batch_op.drop_column('kind')
