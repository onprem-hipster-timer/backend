"""add consent to user_profile

user_profile에 동의한 약관 버전(consent_version)과 시각(consented_at)을 더한다.
기존 행은 NULL이라 다음 로그인 때 동의를 다시 받는다.

회귀 테스트: tests/db/test_user_profile_consent_migration.py

Revision ID: a7c3e9f1b2d4
Revises: 314620d41758
Create Date: 2026-11-11 12:00:00.000000+09:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'a7c3e9f1b2d4'
down_revision: Union[str, None] = '314620d41758'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('user_profile') as batch_op:
        batch_op.add_column(sa.Column('consent_version', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column('consented_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('user_profile') as batch_op:
        batch_op.drop_column('consented_at')
        batch_op.drop_column('consent_version')
