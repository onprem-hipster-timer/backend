"""add analytics consent to user_profile

user_profile에 회원의 사용성 분석 동의(analytics_consent: granted, denied)와 마지막으로 바꾼 시각
(analytics_consent_updated_at)을 더한다. 둘 다 NULL을 허용하고 기존 행은 NULL(고르지 않음)이다.
앱 시작의 create_all이 컬럼을 먼저 만들었으면 건너뛴다.
downgrade는 두 컬럼을 지운다.

회귀 테스트: tests/db/test_user_profile_analytics_consent_migration.py

Revision ID: 73e8f92c2d27
Revises: b3e7c1d9f4a2
Create Date: 2026-11-17 12:00:00.000000+09:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '73e8f92c2d27'
down_revision: Union[str, None] = 'b3e7c1d9f4a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ANALYTICS_CONSENT_TYPE = sa.String(length=7)


def upgrade() -> None:
    existing = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('user_profile')}
    with op.batch_alter_table('user_profile') as batch_op:
        if 'analytics_consent' not in existing:
            batch_op.add_column(sa.Column('analytics_consent', ANALYTICS_CONSENT_TYPE, nullable=True))
        if 'analytics_consent_updated_at' not in existing:
            batch_op.add_column(sa.Column('analytics_consent_updated_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('user_profile') as batch_op:
        batch_op.drop_column('analytics_consent_updated_at')
        batch_op.drop_column('analytics_consent')
