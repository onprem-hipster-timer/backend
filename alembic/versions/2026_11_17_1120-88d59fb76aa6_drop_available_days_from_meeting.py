"""drop available_days from meeting

meeting의 available_days를 없앤다. 미팅의 날짜는 start_date~end_date에서 excluded_dates를 뺀 날이다.
앱 시작의 create_all이 컬럼 없이 만들었으면 건너뛴다.
downgrade는 available_days를 미팅 날짜의 요일로 채운다. 같은 요일에 미팅 날짜와 제외 날짜가 함께 있으면 그 요일은 들어간다.

회귀 테스트: tests/db/test_meeting_excluded_dates_migration.py

Revision ID: 88d59fb76aa6
Revises: 05f01afca5ea
Create Date: 2026-11-17 11:20:00.000000+09:00

"""
from datetime import date, timedelta
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '88d59fb76aa6'
down_revision: Union[str, None] = '05f01afca5ea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if 'available_days' not in {c['name'] for c in sa.inspect(op.get_bind()).get_columns('meeting')}:
        return

    with op.batch_alter_table('meeting') as batch_op:
        batch_op.drop_column('available_days')


def _weekdays(start_date: date, end_date: date, excluded_dates: list[str]) -> list[int]:
    """미팅 날짜(start_date~end_date에서 excluded_dates를 뺀 날)의 요일"""
    excluded = {date.fromisoformat(day) for day in excluded_dates}
    days = (start_date + timedelta(days=offset) for offset in range((end_date - start_date).days + 1))
    return sorted({day.weekday() for day in days if day not in excluded})


def downgrade() -> None:
    bind = op.get_bind()
    with op.batch_alter_table('meeting') as batch_op:
        batch_op.add_column(sa.Column('available_days', sa.JSON(), nullable=True))

    meeting = sa.table(
        'meeting',
        sa.column('id'),
        sa.column('start_date', sa.Date()),
        sa.column('end_date', sa.Date()),
        sa.column('excluded_dates', sa.JSON()),
        sa.column('available_days', sa.JSON()),
    )
    rows = bind.execute(
        sa.select(meeting.c.id, meeting.c.start_date, meeting.c.end_date, meeting.c.excluded_dates)
    ).all()
    if rows:
        bind.execute(
            sa.update(meeting)
            .where(meeting.c.id == sa.bindparam('_id'))
            .values(available_days=sa.bindparam('_available_days')),
            [
                {'_id': row.id, '_available_days': _weekdays(row.start_date, row.end_date, row.excluded_dates)}
                for row in rows
            ],
        )

    with op.batch_alter_table('meeting') as batch_op:
        batch_op.alter_column('available_days', existing_type=sa.JSON(), nullable=False)
