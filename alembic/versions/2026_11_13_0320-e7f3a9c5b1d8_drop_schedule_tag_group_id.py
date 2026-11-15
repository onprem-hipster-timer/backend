"""drop schedule tag_group_id

일정의 tag_group_id(태그 그룹 직접 연결)를 지운다. 일정에서 만드는 할 일의 그룹은 할 일 그룹으로 정한다.
옛 FK는 DB를 만든 경로마다 이름이 달라 이름으로 지우지 않고 컬럼째 지운다.

회귀 테스트: tests/db/test_todo_group_migration.py

Revision ID: e7f3a9c5b1d8
Revises: d4a8b2c6e1f9
Create Date: 2026-11-13 03:20:00.000000+09:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7f3a9c5b1d8'
down_revision: Union[str, None] = 'd4a8b2c6e1f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _schedule_columns() -> set[str]:
    return {c['name'] for c in sa.inspect(op.get_bind()).get_columns('schedule')}


def upgrade() -> None:
    if 'tag_group_id' not in _schedule_columns():
        return
    with op.batch_alter_table('schedule') as batch_op:
        batch_op.drop_column('tag_group_id')


def downgrade() -> None:
    if 'tag_group_id' in _schedule_columns():
        return
    with op.batch_alter_table('schedule') as batch_op:
        batch_op.add_column(sa.Column('tag_group_id', sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            'fk_schedule_tag_group_id', 'tag_group', ['tag_group_id'], ['id'], ondelete='SET NULL',
        )
