"""add analytics to consent

consent에 사용성 분석 동의(analytics: 선택, true·false)와 마지막으로 정한 시각(analytics_updated_at)을 더한다.
둘 다 NULL을 허용하고 기존 행은 NULL(고르지 않음)이다. 앱 시작의 create_all이 컬럼을 먼저 만들었으면 건너뛴다.
downgrade는 두 컬럼을 지운다.

회귀 테스트: tests/db/test_consent_analytics_migration.py

Revision ID: 34f0c570658d
Revises: b3e7c1d9f4a2
Create Date: 2026-11-18 12:00:00.000000+09:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '34f0c570658d'
down_revision: Union[str, None] = 'b3e7c1d9f4a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    existing = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('consent')}
    with op.batch_alter_table('consent') as batch_op:
        if 'analytics' not in existing:
            batch_op.add_column(sa.Column('analytics', sa.Boolean(), nullable=True))
        if 'analytics_updated_at' not in existing:
            batch_op.add_column(sa.Column('analytics_updated_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('consent') as batch_op:
        batch_op.drop_column('analytics_updated_at')
        batch_op.drop_column('analytics')
