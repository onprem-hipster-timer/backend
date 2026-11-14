"""add guest

리소스 하나에 속한 게스트(Kratos identity ↔ 리소스, 리소스 안에서 겹치지 않는 이름) guest 테이블을 만든다.
앱 시작의 create_all이 먼저 만들었을 수 있으므로 없을 때만 만든다.

회귀 테스트: tests/db/test_guest_migration.py

Revision ID: f2b6d8a4c3e7
Revises: aeb221d93ba3
Create Date: 2026-11-14 12:00:00.000000+09:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'f2b6d8a4c3e7'
down_revision: Union[str, None] = 'aeb221d93ba3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if 'guest' in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        'guest',
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('identity_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('resource_type', sa.String(length=8), nullable=False),
        sa.Column('resource_id', sa.Uuid(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('resource_type', 'resource_id', 'name', name='uq_guest_resource_name'),
    )
    op.create_index(op.f('ix_guest_id'), 'guest', ['id'], unique=False)
    op.create_index(op.f('ix_guest_identity_id'), 'guest', ['identity_id'], unique=True)
    op.create_index('ix_guest_resource', 'guest', ['resource_type', 'resource_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_guest_resource', table_name='guest')
    op.drop_index(op.f('ix_guest_identity_id'), table_name='guest')
    op.drop_index(op.f('ix_guest_id'), table_name='guest')
    op.drop_table('guest')
