"""move todos to todo group

할 일이 태그 그룹(todo.tag_group_id) 대신 할 일 그룹(todo.todo_group_id)에 속하게 한다.

1. 할 일이 있는 태그 그룹을 같은 id로 todo_group에 복사한다(이름·색·설명·시각).
2. todo.todo_group_id를 nullable로 더해 tag_group_id 값으로 채운다.
3. 예전 데이터를 정리한다.
   - 할 일 소유자와 그룹 소유자가 다르면(생성 때 그룹 소유를 확인하지 않던 시절) 할 일 소유자의 새 그룹으로 옮긴다.
   - 부모와 그룹이 다르면(그룹만 바꾸는 수정을 검사하지 않던 시절) 부모 연결을 끊는다.
4. todo_group_id를 NOT NULL·FK(fk_todo_todo_group_id, RESTRICT)·인덱스로 만들고 tag_group_id를 지운다.

옛 FK는 DB를 만든 경로마다 이름이 달라 이름으로 지우지 않고 컬럼째 지운다.
SQLite는 DDL을 트랜잭션으로 묶지 않아(transactional_ddl=False) 중간에 실패하면 반쯤 바뀐 DB가 남는다.

회귀 테스트: tests/db/test_todo_group_migration.py

Revision ID: d4a8b2c6e1f9
Revises: c1d5e9a3f7b2
Create Date: 2026-11-13 03:10:00.000000+09:00

"""
import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4a8b2c6e1f9'
down_revision: Union[str, None] = 'c1d5e9a3f7b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_GROUP_COLUMNS = ('id', 'owner_id', 'name', 'color', 'description', 'created_at', 'updated_at')


def _group_table(name: str) -> sa.TableClause:
    return sa.table(
        name,
        sa.column('id', sa.Uuid()),
        sa.column('owner_id', sa.String()),
        sa.column('name', sa.String()),
        sa.column('color', sa.String()),
        sa.column('description', sa.String()),
        sa.column('created_at', sa.DateTime()),
        sa.column('updated_at', sa.DateTime()),
    )


def _todo_table(group_column: str) -> sa.TableClause:
    return sa.table(
        'todo',
        sa.column('id', sa.Uuid()),
        sa.column('owner_id', sa.String()),
        sa.column('parent_id', sa.Uuid()),
        sa.column(group_column, sa.Uuid()),
    )


def _todo_columns() -> set[str]:
    return {c['name'] for c in sa.inspect(op.get_bind()).get_columns('todo')}


def _todo_indexes() -> set[str]:
    return {i['name'] for i in sa.inspect(op.get_bind()).get_indexes('todo')}


def _copy_referenced_groups(source: str, target: str, group_column: str) -> None:
    """todo.<group_column>이 가리키는 source 그룹 중 target에 없는 것을 같은 id로 복사한다"""
    source_t, target_t, todo_t = _group_table(source), _group_table(target), _todo_table(group_column)
    referenced = sa.select(todo_t.c[group_column]).distinct()
    existing = sa.select(target_t.c.id)
    op.get_bind().execute(
        target_t.insert().from_select(
            list(_GROUP_COLUMNS),
            sa.select(*(source_t.c[name] for name in _GROUP_COLUMNS))
            .where(source_t.c.id.in_(referenced))
            .where(source_t.c.id.not_in(existing)),
        )
    )


def _give_foreign_owned_todos_their_own_group() -> None:
    """그룹 소유자와 다른 사람의 할 일을 그 사람 소유의 새 그룹(같은 이름·색·설명)으로 옮긴다"""
    bind = op.get_bind()
    group_t, todo_t = _group_table('todo_group'), _todo_table('todo_group_id')
    pairs = bind.execute(
        sa.select(todo_t.c.owner_id, todo_t.c.todo_group_id)
        .distinct()
        .select_from(todo_t.join(group_t, todo_t.c.todo_group_id == group_t.c.id))
        .where(todo_t.c.owner_id != group_t.c.owner_id)
    ).all()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for owner_id, group_id in pairs:
        source = bind.execute(
            sa.select(group_t.c.name, group_t.c.color, group_t.c.description).where(group_t.c.id == group_id)
        ).one()
        new_id = uuid.uuid4()
        bind.execute(group_t.insert().values(
            id=new_id, owner_id=owner_id, name=source.name, color=source.color,
            description=source.description, created_at=now, updated_at=now,
        ))
        bind.execute(
            todo_t.update()
            .where(todo_t.c.owner_id == owner_id)
            .where(todo_t.c.todo_group_id == group_id)
            .values(todo_group_id=new_id)
        )


def _detach_children_in_other_groups(group_column: str) -> None:
    """부모와 그룹이 다른 할 일의 부모 연결을 끊는다"""
    todo_t = _todo_table(group_column)
    parent = todo_t.alias('parent')
    parent_group = sa.select(parent.c[group_column]).where(parent.c.id == todo_t.c.parent_id).scalar_subquery()
    op.get_bind().execute(
        todo_t.update()
        .where(todo_t.c.parent_id.is_not(None))
        .where(todo_t.c[group_column] != parent_group)
        .values(parent_id=None)
    )


def upgrade() -> None:
    if 'tag_group_id' not in _todo_columns():
        return

    _copy_referenced_groups('tag_group', 'todo_group', 'tag_group_id')

    if 'todo_group_id' not in _todo_columns():
        with op.batch_alter_table('todo') as batch_op:
            batch_op.add_column(sa.Column('todo_group_id', sa.Uuid(), nullable=True))
    todo_t = sa.table('todo', sa.column('todo_group_id', sa.Uuid()), sa.column('tag_group_id', sa.Uuid()))
    op.get_bind().execute(todo_t.update().values(todo_group_id=todo_t.c.tag_group_id))

    _give_foreign_owned_todos_their_own_group()
    _detach_children_in_other_groups('todo_group_id')

    indexes = _todo_indexes()
    with op.batch_alter_table('todo') as batch_op:
        if 'ix_todo_tag_group_id' in indexes:
            batch_op.drop_index('ix_todo_tag_group_id')
        batch_op.drop_column('tag_group_id')
        batch_op.alter_column('todo_group_id', existing_type=sa.Uuid(), nullable=False)
        batch_op.create_foreign_key(
            'fk_todo_todo_group_id', 'todo_group', ['todo_group_id'], ['id'], ondelete='RESTRICT',
        )
        if 'ix_todo_todo_group_id' not in indexes:
            batch_op.create_index('ix_todo_todo_group_id', ['todo_group_id'], unique=False)


def downgrade() -> None:
    if 'todo_group_id' not in _todo_columns():
        return

    _copy_referenced_groups('todo_group', 'tag_group', 'todo_group_id')

    with op.batch_alter_table('todo') as batch_op:
        batch_op.add_column(sa.Column('tag_group_id', sa.Uuid(), nullable=True))
    todo_t = sa.table('todo', sa.column('todo_group_id', sa.Uuid()), sa.column('tag_group_id', sa.Uuid()))
    op.get_bind().execute(todo_t.update().values(tag_group_id=todo_t.c.todo_group_id))

    indexes = _todo_indexes()
    with op.batch_alter_table('todo') as batch_op:
        if 'ix_todo_todo_group_id' in indexes:
            batch_op.drop_index('ix_todo_todo_group_id')
        batch_op.drop_column('todo_group_id')
        batch_op.alter_column('tag_group_id', existing_type=sa.Uuid(), nullable=False)
        batch_op.create_foreign_key(
            'fk_todo_tag_group_id', 'tag_group', ['tag_group_id'], ['id'], ondelete='RESTRICT',
        )
        batch_op.create_index('ix_todo_tag_group_id', ['tag_group_id'], unique=False)
