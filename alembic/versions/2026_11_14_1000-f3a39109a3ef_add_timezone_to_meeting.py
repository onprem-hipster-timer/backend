"""add timezone to meeting

meeting에 IANA 시간대 이름(timezone)을 더한다. 기존 행은 'UTC'로 채우고, 채운 뒤 서버 기본값은 없앤다.
앱 시작의 create_all이 컬럼을 먼저 만들었으면 건너뛴다.

회귀 테스트: tests/db/test_meeting_timezone_migration.py

Revision ID: f3a39109a3ef
Revises: 3f1fcd3dae5f
Create Date: 2026-11-14 10:00:00.000000+09:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'f3a39109a3ef'
down_revision: Union[str, None] = '3f1fcd3dae5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columns = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('meeting')}
    if 'timezone' in columns:
        return

    with op.batch_alter_table('meeting') as batch_op:
        batch_op.add_column(sa.Column(
            'timezone', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='UTC',
        ))
    with op.batch_alter_table('meeting') as batch_op:
        batch_op.alter_column('timezone', server_default=None)


def downgrade() -> None:
    with op.batch_alter_table('meeting') as batch_op:
        batch_op.drop_column('timezone')
