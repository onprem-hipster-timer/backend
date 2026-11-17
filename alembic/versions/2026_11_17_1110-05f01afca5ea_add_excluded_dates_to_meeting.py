"""add excluded_dates to meeting

meeting에 기간에서 빼는 날짜(excluded_dates, ISO 날짜 문자열의 JSON 배열)를 더한다. 기존 행은 기간 안에서 요일이
available_days에 없는 날로 채운다. 기간의 첫날·마지막 날이 그런 날이면 start_date·end_date를 available_days에 있는
첫날·마지막 날로 줄인다. 기간 안에 available_days에 있는 날이 없으면 기간을 그대로 두고 빈 목록으로 채운다.
앱 시작의 create_all이 컬럼을 먼저 만들었으면 건너뛴다.
downgrade는 excluded_dates만 없앤다. 줄인 기간은 그대로 둔다.

회귀 테스트: tests/db/test_meeting_excluded_dates_migration.py

Revision ID: 05f01afca5ea
Revises: f10bc70bcb28
Create Date: 2026-11-17 11:10:00.000000+09:00

"""
from datetime import date, timedelta
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '05f01afca5ea'
down_revision: Union[str, None] = 'f10bc70bcb28'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _excluded(start_date: date, end_date: date, available_days: list[int]) -> tuple[date, date, list[str]]:
    """(start_date, end_date, excluded_dates): 앞뒤를 미팅 날짜까지 줄이고 사이의 미팅 날짜가 아닌 날을 뺀다"""
    days = [start_date + timedelta(days=offset) for offset in range((end_date - start_date).days + 1)]
    meeting_days = [day for day in days if day.weekday() in available_days]
    if not meeting_days:
        return start_date, end_date, []
    first, last = meeting_days[0], meeting_days[-1]
    return first, last, [day.isoformat() for day in days if first < day < last and day not in meeting_days]


def upgrade() -> None:
    bind = op.get_bind()
    if 'excluded_dates' in {c['name'] for c in sa.inspect(bind).get_columns('meeting')}:
        return

    with op.batch_alter_table('meeting') as batch_op:
        batch_op.add_column(sa.Column('excluded_dates', sa.JSON(), nullable=True))

    meeting = sa.table(
        'meeting',
        sa.column('id'),
        sa.column('start_date', sa.Date()),
        sa.column('end_date', sa.Date()),
        sa.column('available_days', sa.JSON()),
        sa.column('excluded_dates', sa.JSON()),
    )
    rows = bind.execute(
        sa.select(meeting.c.id, meeting.c.start_date, meeting.c.end_date, meeting.c.available_days)
    ).all()
    if rows:
        statement = (
            sa.update(meeting)
            .where(meeting.c.id == sa.bindparam('_id'))
            .values(
                start_date=sa.bindparam('_start_date'),
                end_date=sa.bindparam('_end_date'),
                excluded_dates=sa.bindparam('_excluded_dates'),
            )
        )
        parameters = []
        for row in rows:
            start_date, end_date, excluded_dates = _excluded(row.start_date, row.end_date, row.available_days)
            parameters.append({
                '_id': row.id, '_start_date': start_date, '_end_date': end_date, '_excluded_dates': excluded_dates,
            })
        bind.execute(statement, parameters)

    with op.batch_alter_table('meeting') as batch_op:
        batch_op.alter_column('excluded_dates', existing_type=sa.JSON(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table('meeting') as batch_op:
        batch_op.drop_column('excluded_dates')
