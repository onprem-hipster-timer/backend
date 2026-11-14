"""move holiday day ends to midnight

공휴일 구간은 [start_date, end_date)이고 end_date는 다음 날 00:00(KST)이다.
holidays에서 end_date + 1마이크로초가 정각 초이고 end_date - start_date + 1마이크로초가
24시간의 양의 배수인 행은 end_date에 1마이크로초를 더한다.
downgrade는 end_date - start_date가 24시간의 양의 배수인 행에서 1마이크로초를 뺀다.
holidays 테이블이 없으면 아무것도 하지 않는다.

회귀 테스트: tests/db/test_holiday_day_end_migration.py

Revision ID: a9e1c7d3f5b2
Revises: f2b6d8a4c0e7
Create Date: 2026-11-14 09:10:00.000000+09:00

"""
from datetime import datetime, timedelta
from typing import Callable, Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a9e1c7d3f5b2'
down_revision: Union[str, None] = 'f2b6d8a4c0e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DAY = timedelta(days=1)
_MICROSECOND = timedelta(microseconds=1)


def _whole_days(span: timedelta) -> bool:
    return span > timedelta(0) and span % _DAY == timedelta(0)


def _ends_one_microsecond_before_day(start: datetime, end: datetime) -> bool:
    return end.microsecond == 999999 and _whole_days(end - start + _MICROSECOND)


def _spans_whole_days(start: datetime, end: datetime) -> bool:
    return _whole_days(end - start)


def _shift_end_date(qualifies: Callable[[datetime, datetime], bool], delta: timedelta) -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table('holidays'):
        return
    table = sa.table(
        'holidays',
        sa.column('id', sa.Uuid()),
        sa.column('start_date', sa.DateTime()),
        sa.column('end_date', sa.DateTime()),
    )
    rows = bind.execute(sa.select(table.c.id, table.c.start_date, table.c.end_date)).all()
    for row_id, start, end in rows:
        if qualifies(start, end):
            bind.execute(table.update().where(table.c.id == row_id).values(end_date=end + delta))


def upgrade() -> None:
    _shift_end_date(_ends_one_microsecond_before_day, _MICROSECOND)


def downgrade() -> None:
    _shift_end_date(_spans_whole_days, -_MICROSECOND)
