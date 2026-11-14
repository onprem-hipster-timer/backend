"""unique meeting participant per user

meeting_participant에 UNIQUE (meeting_id, user_id)를 더한다. 그 전에 (meeting_id, user_id)마다
가장 나중에 만든 참여자(created_at, 같으면 id가 큰 쪽)만 남기고 나머지와 그 가능 시간을 지운다.
user_id가 NULL인 행은 건드리지 않는다. 앱 시작의 create_all이 제약을 먼저 만들었으면 건너뛴다.
downgrade는 제약만 없애고 지운 행은 되살리지 않는다.

회귀 테스트: tests/db/test_meeting_participant_unique_migration.py

Revision ID: 3f1fcd3dae5f
Revises: e7f3a9c5b1d8
Create Date: 2026-11-14 09:00:00.000000+09:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3f1fcd3dae5f'
down_revision: Union[str, None] = 'e7f3a9c5b1d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONSTRAINT = 'uq_meeting_participant_meeting_user'

_DUPLICATES = """
    SELECT id FROM (
        SELECT id, ROW_NUMBER() OVER (
            PARTITION BY meeting_id, user_id ORDER BY created_at DESC, id DESC
        ) AS rn
        FROM meeting_participant
        WHERE user_id IS NOT NULL
    ) ranked
    WHERE rn > 1
"""


def upgrade() -> None:
    bind = op.get_bind()
    existing = {u['name'] for u in sa.inspect(bind).get_unique_constraints('meeting_participant')}
    if CONSTRAINT in existing:
        return

    op.execute(f"DELETE FROM meeting_time_slot WHERE participant_id IN ({_DUPLICATES})")
    op.execute(f"DELETE FROM meeting_participant WHERE id IN ({_DUPLICATES})")
    with op.batch_alter_table('meeting_participant') as batch_op:
        batch_op.create_unique_constraint(CONSTRAINT, ['meeting_id', 'user_id'])


def downgrade() -> None:
    with op.batch_alter_table('meeting_participant') as batch_op:
        batch_op.drop_constraint(CONSTRAINT, type_='unique')
