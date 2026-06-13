"""add_user_profile_table

Revision ID: a7f3c1d9e2b4
Revises: f087a3c6cc59
Create Date: 2026-06-13 10:00:00.000000+09:00

OIDC sub ↔ 표시정보(display_name, avatar_url) JIT 캐시 테이블.
- email 컬럼 없음(ALLOWED_EMAILS 라이브 매칭 전용, 미영속 원칙).
- friend_code: 외부 공유용 불투명 코드(sub 비노출), unique.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = 'a7f3c1d9e2b4'
down_revision: Union[str, None] = 'f087a3c6cc59'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    # ### UserProfile 테이블 생성 ###
    if 'user_profile' not in tables:
        op.create_table(
            'user_profile',
            sa.Column('sub', sa.String(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.Column('iss', sa.String(), nullable=True),
            sa.Column('display_name', sa.String(), nullable=True),
            sa.Column('avatar_url', sa.String(), nullable=True),
            sa.Column('friend_code', sa.String(), nullable=False),
            sa.Column('email_hash', sa.String(), nullable=True),
            sa.PrimaryKeyConstraint('sub'),
        )
        op.create_index(
            op.f('ix_user_profile_friend_code'),
            'user_profile',
            ['friend_code'],
            unique=True,
        )
        op.create_index(
            op.f('ix_user_profile_email_hash'),
            'user_profile',
            ['email_hash'],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if 'user_profile' in tables:
        try:
            op.drop_index(op.f('ix_user_profile_email_hash'), table_name='user_profile')
        except Exception:
            pass
        try:
            op.drop_index(op.f('ix_user_profile_friend_code'), table_name='user_profile')
        except Exception:
            pass
        op.drop_table('user_profile')
