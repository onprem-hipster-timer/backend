"""meeting time slot utc instants

meeting_time_slot의 slot_date + start_time/end_time(time)을 UTC naive datetime인 start_time/end_time으로 바꾼다.
기존 행은 slot_date + 시각을 UTC로 읽는다. slot_date 컬럼과 인덱스는 없앤다.
앱 시작의 create_all이 새 모양으로 만들었으면 건너뛴다.
downgrade는 시작 시각의 UTC 날짜를 slot_date로 되돌린다. 끝이 다른 날짜인 슬롯의 end_time은 23:59:59.999999가 된다.

회귀 테스트: tests/db/test_meeting_time_slot_instants_migration.py

Revision ID: 911321f82154
Revises: 5fdfd93be2c3
Create Date: 2026-11-14 10:20:00.000000+09:00

"""
from datetime import datetime, time
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '911321f82154'
down_revision: Union[str, None] = '5fdfd93be2c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'meeting_time_slot'
CHECK = 'ck_time_slot_range'
SLOT_DATE_INDEX = 'ix_meeting_time_slot_slot_date'


def _convert(source: list[tuple[str, sa.types.TypeEngine]], target: list[tuple[str, sa.types.TypeEngine]], convert) -> None:
    """source 컬럼 값을 convert로 바꿔 target 컬럼에 쓴다"""
    bind = op.get_bind()
    table = sa.table(TABLE, sa.column('id'), *(sa.column(n, t) for n, t in source + target))
    rows = bind.execute(sa.select(table.c.id, *(table.c[n] for n, _ in source))).all()
    if not rows:
        return
    statement = (
        sa.update(table)
        .where(table.c.id == sa.bindparam('_id'))
        .values({n: sa.bindparam(f'_{n}') for n, _ in target})
    )
    bind.execute(statement, [
        {'_id': row[0], **{f'_{n}': v for (n, _), v in zip(target, convert(*row[1:]))}}
        for row in rows
    ])


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if 'slot_date' not in {c['name'] for c in inspector.get_columns(TABLE)}:
        return
    has_slot_date_index = SLOT_DATE_INDEX in {i['name'] for i in inspector.get_indexes(TABLE)}

    with op.batch_alter_table(TABLE) as batch_op:
        batch_op.add_column(sa.Column('start_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('end_at', sa.DateTime(), nullable=True))

    _convert(
        [('slot_date', sa.Date()), ('start_time', sa.Time()), ('end_time', sa.Time())],
        [('start_at', sa.DateTime()), ('end_at', sa.DateTime())],
        lambda slot_date, start, end: (datetime.combine(slot_date, start), datetime.combine(slot_date, end)),
    )

    with op.batch_alter_table(TABLE) as batch_op:
        if has_slot_date_index:
            batch_op.drop_index(SLOT_DATE_INDEX)
        batch_op.drop_constraint(CHECK, type_='check')
        batch_op.drop_column('slot_date')
        batch_op.drop_column('start_time')
        batch_op.drop_column('end_time')
    with op.batch_alter_table(TABLE) as batch_op:
        batch_op.alter_column('start_at', new_column_name='start_time', existing_type=sa.DateTime(), nullable=False)
        batch_op.alter_column('end_at', new_column_name='end_time', existing_type=sa.DateTime(), nullable=False)
        batch_op.create_check_constraint(CHECK, 'start_time < end_time')


def downgrade() -> None:
    with op.batch_alter_table(TABLE) as batch_op:
        batch_op.add_column(sa.Column('slot_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('start_tod', sa.Time(), nullable=True))
        batch_op.add_column(sa.Column('end_tod', sa.Time(), nullable=True))

    _convert(
        [('start_time', sa.DateTime()), ('end_time', sa.DateTime())],
        [('slot_date', sa.Date()), ('start_tod', sa.Time()), ('end_tod', sa.Time())],
        lambda start, end: (
            start.date(),
            start.time(),
            end.time() if end.date() == start.date() else time.max,
        ),
    )

    with op.batch_alter_table(TABLE) as batch_op:
        batch_op.drop_constraint(CHECK, type_='check')
        batch_op.drop_column('start_time')
        batch_op.drop_column('end_time')
    with op.batch_alter_table(TABLE) as batch_op:
        batch_op.alter_column('slot_date', existing_type=sa.Date(), nullable=False)
        batch_op.alter_column('start_tod', new_column_name='start_time', existing_type=sa.Time(), nullable=False)
        batch_op.alter_column('end_tod', new_column_name='end_time', existing_type=sa.Time(), nullable=False)
        batch_op.create_check_constraint(CHECK, 'start_time < end_time')
        batch_op.create_index(SLOT_DATE_INDEX, ['slot_date'], unique=False)
