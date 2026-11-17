"""add allow_guests to meeting

meeting에 게스트를 받는지(allow_guests, 기본 false)를 더한다. 기존 행은 false다.
앱 시작의 create_all이 컬럼을 먼저 만들었으면 건너뛴다.

회귀 테스트: tests/db/test_meeting_guest_migration.py

Revision ID: a4c8e2f6b1d3
Revises: 73e8f92c2d27
Create Date: 2026-11-17 10:00:00.000000+09:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4c8e2f6b1d3'
down_revision: Union[str, None] = '73e8f92c2d27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columns = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('meeting')}
    if 'allow_guests' in columns:
        return

    with op.batch_alter_table('meeting') as batch_op:
        batch_op.add_column(sa.Column('allow_guests', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    with op.batch_alter_table('meeting') as batch_op:
        batch_op.drop_column('allow_guests')
