"""move schedule day ends to midnight

일정 구간은 [start_time, end_time)이고 하루의 끝은 다음 날 00:00이다.
schedule과 scheduleexception에서 end_time이 hh:59:00.000000이고 end_time - start_time + 1분이
24시간의 양의 배수인 행은 end_time에 1분을 더한다.
downgrade는 end_time - start_time이 24시간의 양의 배수인 행에서 1분을 뺀다.
행 선택은 SQLite와 PostgreSQL에서 같게 동작하도록 Python에서 한다.

회귀 테스트: tests/db/test_schedule_day_end_migration.py

Revision ID: f2b6d8a4c0e7
Revises: e7f3a9c5b1d8
Create Date: 2026-11-14 09:00:00.000000+09:00

"""
from datetime import datetime, timedelta
from typing import Callable, Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2b6d8a4c0e7'
down_revision: Union[str, None] = 'e7f3a9c5b1d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DAY = timedelta(days=1)
_MINUTE = timedelta(minutes=1)


def _whole_days(span: timedelta) -> bool:
    return span > timedelta(0) and span % _DAY == timedelta(0)


def _ends_one_minute_before_day(start: datetime, end: datetime) -> bool:
    return (end.minute, end.second, end.microsecond) == (59, 0, 0) and _whole_days(end - start + _MINUTE)


def _spans_whole_days(start: datetime, end: datetime) -> bool:
    return _whole_days(end - start)


def _shift_end_time(qualifies: Callable[[datetime, datetime], bool], delta: timedelta) -> None:
    bind = op.get_bind()
    for name in ('schedule', 'scheduleexception'):
        table = sa.table(
            name,
            sa.column('id', sa.Uuid()),
            sa.column('start_time', sa.DateTime()),
            sa.column('end_time', sa.DateTime()),
        )
        rows = bind.execute(
            sa.select(table.c.id, table.c.start_time, table.c.end_time)
            .where(table.c.start_time.is_not(None))
            .where(table.c.end_time.is_not(None))
        ).all()
        for row_id, start, end in rows:
            if qualifies(start, end):
                bind.execute(
                    table.update().where(table.c.id == row_id).values(end_time=end + delta)
                )


def upgrade() -> None:
    _shift_end_time(_ends_one_minute_before_day, _MINUTE)


def downgrade() -> None:
    _shift_end_time(_spans_whole_days, -_MINUTE)
