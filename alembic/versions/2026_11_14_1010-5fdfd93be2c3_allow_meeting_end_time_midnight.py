"""allow meeting end_time midnight

ck_meeting_time_range가 end_time 00:00(하루의 끝)을 받도록 바꾼다.
앱 시작의 create_all이 새 제약을 먼저 만들었으면 건너뛴다.
downgrade는 end_time이 00:00인 미팅의 end_time을 23:59:59로 바꾼 뒤 이전 제약으로 되돌린다.

회귀 테스트: tests/db/test_meeting_end_time_midnight_migration.py

Revision ID: 5fdfd93be2c3
Revises: f3a39109a3ef
Create Date: 2026-11-14 10:10:00.000000+09:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5fdfd93be2c3'
down_revision: Union[str, None] = 'f3a39109a3ef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONSTRAINT = 'ck_meeting_time_range'
# SQLite는 time을 'HH:MM:SS.ffffff' 문자열로 저장한다
MIDNIGHT = "('00:00:00', '00:00:00.000000')"
NEW_CHECK = f"start_time < end_time OR end_time IN {MIDNIGHT}"
OLD_CHECK = "start_time < end_time"


def _current_check() -> str | None:
    for check in sa.inspect(op.get_bind()).get_check_constraints('meeting'):
        if check['name'] == CONSTRAINT:
            return check['sqltext']
    return None


def upgrade() -> None:
    if '00:00:00' in (_current_check() or ''):
        return

    with op.batch_alter_table('meeting') as batch_op:
        batch_op.drop_constraint(CONSTRAINT, type_='check')
        batch_op.create_check_constraint(CONSTRAINT, NEW_CHECK)


def downgrade() -> None:
    op.execute(f"UPDATE meeting SET end_time = '23:59:59' WHERE end_time IN {MIDNIGHT}")
    with op.batch_alter_table('meeting') as batch_op:
        batch_op.drop_constraint(CONSTRAINT, type_='check')
        batch_op.create_check_constraint(CONSTRAINT, OLD_CHECK)
