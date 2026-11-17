"""add mode to meeting

meeting에 답하는 방식(mode: hourly, daily, weekly)을 더한다. 기존 행은 start_time이 00:00이고 기간이 7일이면 weekly,
start_time이 00:00이면 daily, 그 밖은 hourly로 채운 뒤 NOT NULL로 바꾼다.
앱 시작의 create_all이 컬럼을 먼저 만들었으면 건너뛴다.

회귀 테스트: tests/db/test_meeting_mode_migration.py

Revision ID: f10bc70bcb28
Revises: b5d9f3a7c2e4
Create Date: 2026-11-17 11:00:00.000000+09:00

"""
from datetime import date, time
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f10bc70bcb28'
down_revision: Union[str, None] = 'b5d9f3a7c2e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MODE_TYPE = sa.String(length=6)


def _mode(start_date: date, end_date: date, start_time: time) -> str:
    if start_time != time(0):
        return 'hourly'
    return 'weekly' if (end_date - start_date).days == 6 else 'daily'


def upgrade() -> None:
    bind = op.get_bind()
    if 'mode' in {c['name'] for c in sa.inspect(bind).get_columns('meeting')}:
        return

    with op.batch_alter_table('meeting') as batch_op:
        batch_op.add_column(sa.Column('mode', MODE_TYPE, nullable=True))

    meeting = sa.table(
        'meeting',
        sa.column('id'),
        sa.column('start_date', sa.Date()),
        sa.column('end_date', sa.Date()),
        sa.column('start_time', sa.Time()),
        sa.column('mode', MODE_TYPE),
    )
    rows = bind.execute(sa.select(meeting.c.id, meeting.c.start_date, meeting.c.end_date, meeting.c.start_time)).all()
    if rows:
        bind.execute(
            sa.update(meeting).where(meeting.c.id == sa.bindparam('_id')).values(mode=sa.bindparam('_mode')),
            [{'_id': row.id, '_mode': _mode(row.start_date, row.end_date, row.start_time)} for row in rows],
        )

    with op.batch_alter_table('meeting') as batch_op:
        batch_op.alter_column('mode', existing_type=MODE_TYPE, nullable=False)


def downgrade() -> None:
    with op.batch_alter_table('meeting') as batch_op:
        batch_op.drop_column('mode')
