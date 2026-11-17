"""add guest_id to meeting_participant

meeting_participant에 게스트 참여자의 게스트 행(guest_id)을 더한다. guest.id를 참조하고 게스트 행을 지우면 참여자도
지운다(ON DELETE CASCADE, 가능 시간은 참여자를 따라 지워진다). 게스트마다 참여자는 하나(UNIQUE guest_id)이고,
user_id와 guest_id를 함께 둘 수 없다(CHECK). 기존 행의 guest_id는 NULL이다.
앱 시작의 create_all이 컬럼을 먼저 만들었으면 건너뛴다.

회귀 테스트: tests/db/test_meeting_guest_migration.py

Revision ID: b5d9f3a7c2e4
Revises: a4c8e2f6b1d3
Create Date: 2026-11-17 10:10:00.000000+09:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b5d9f3a7c2e4'
down_revision: Union[str, None] = 'a4c8e2f6b1d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FOREIGN_KEY = 'fk_meeting_participant_guest_id'
UNIQUE = 'uq_meeting_participant_guest'
CHECK = 'ck_meeting_participant_user_or_guest'


def upgrade() -> None:
    columns = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('meeting_participant')}
    if 'guest_id' in columns:
        return

    with op.batch_alter_table('meeting_participant') as batch_op:
        batch_op.add_column(sa.Column('guest_id', sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(FOREIGN_KEY, 'guest', ['guest_id'], ['id'], ondelete='CASCADE')
        batch_op.create_unique_constraint(UNIQUE, ['guest_id'])
        batch_op.create_check_constraint(CHECK, 'user_id IS NULL OR guest_id IS NULL')


def downgrade() -> None:
    with op.batch_alter_table('meeting_participant') as batch_op:
        batch_op.drop_constraint(CHECK, type_='check')
        batch_op.drop_constraint(UNIQUE, type_='unique')
        batch_op.drop_constraint(FOREIGN_KEY, type_='foreignkey')
        batch_op.drop_column('guest_id')
