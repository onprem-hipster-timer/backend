"""add todo group

할 일을 담는 todo_group 테이블을 만든다. 사용자당 기본 그룹(is_default)은 부분 unique 인덱스로 하나만 둔다.
앱 시작의 create_all이 먼저 만들었을 수 있으므로 없을 때만 만든다.

회귀 테스트: tests/db/test_todo_group_migration.py

Revision ID: c1d5e9a3f7b2
Revises: b8d2f4a6c1e3
Create Date: 2026-11-13 03:00:00.000000+09:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'c1d5e9a3f7b2'
down_revision: Union[str, None] = 'b8d2f4a6c1e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if 'todo_group' in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        'todo_group',
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('color', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('is_default', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_todo_group_id'), 'todo_group', ['id'], unique=False)
    op.create_index(op.f('ix_todo_group_owner_id'), 'todo_group', ['owner_id'], unique=False)
    op.create_index(
        'uq_todo_group_owner_default',
        'todo_group',
        ['owner_id'],
        unique=True,
        postgresql_where=sa.text('is_default'),
        sqlite_where=sa.text('is_default'),
    )


def downgrade() -> None:
    op.drop_index('uq_todo_group_owner_default', table_name='todo_group')
    op.drop_index(op.f('ix_todo_group_owner_id'), table_name='todo_group')
    op.drop_index(op.f('ix_todo_group_id'), table_name='todo_group')
    op.drop_table('todo_group')
