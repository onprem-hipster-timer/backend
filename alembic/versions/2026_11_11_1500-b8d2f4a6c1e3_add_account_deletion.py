"""add account deletion

user_profile에 탈퇴 신청 시각(deletion_requested_at)을 더하고, 파기한 계정의 sub를 두는
account_deletion 테이블을 만든다. 기존 행은 NULL이라 탈퇴 신청 상태가 아니다.

회귀 테스트: tests/db/test_account_deletion_migration.py

Revision ID: b8d2f4a6c1e3
Revises: a7c3e9f1b2d4
Create Date: 2026-11-11 15:00:00.000000+09:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'b8d2f4a6c1e3'
down_revision: Union[str, None] = 'a7c3e9f1b2d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('user_profile') as batch_op:
        batch_op.add_column(sa.Column('deletion_requested_at', sa.DateTime(), nullable=True))
        batch_op.create_index(op.f('ix_user_profile_deletion_requested_at'), ['deletion_requested_at'], unique=False)

    op.create_table(
        'account_deletion',
        sa.Column('sub', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('purged_at', sa.DateTime(), nullable=False),
        sa.Column('kratos_deleted_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('sub'),
    )


def downgrade() -> None:
    op.drop_table('account_deletion')
    with op.batch_alter_table('user_profile') as batch_op:
        batch_op.drop_index(op.f('ix_user_profile_deletion_requested_at'))
        batch_op.drop_column('deletion_requested_at')
