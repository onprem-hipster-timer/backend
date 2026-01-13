"""Change todo parent_id FK from CASCADE to SET NULL

Revision ID: 1f4bc4f1de04
Revises: 9b9bdc029ff3
Create Date: 2026-01-11 16:52:00.000000+09:00

부모 Todo 삭제 시 자식 Todo가 함께 삭제되지 않고
parent_id가 NULL로 설정되어 루트로 승격되도록 변경.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = '1f4bc4f1de04'
down_revision: Union[str, None] = '9b9bdc029ff3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    parent_id FK의 ondelete를 CASCADE → SET NULL로 변경.
    
    SQLite는 ALTER TABLE로 FK 변경을 지원하지 않으므로
    batch_alter_table을 사용하여 테이블 재생성으로 처리.
    """
    bind = op.get_bind()
    inspector = inspect(bind)

    # 기존 FK 제약 조건 확인
    fks = inspector.get_foreign_keys('todo')
    parent_fk_name = None
    for fk in fks:
        if fk.get('constrained_columns') == ['parent_id']:
            parent_fk_name = fk.get('name')
            break

    with op.batch_alter_table('todo', schema=None) as batch_op:
        # 기존 FK 삭제 (이름이 있는 경우)
        if parent_fk_name:
            batch_op.drop_constraint(parent_fk_name, type_='foreignkey')

        # 새 FK 생성: ondelete='SET NULL'
        batch_op.create_foreign_key(
            'fk_todo_parent_id',  # 명시적 이름 부여
            'todo',
            ['parent_id'],
            ['id'],
            ondelete='SET NULL'
        )


def downgrade() -> None:
    """
    원복: parent_id FK의 ondelete를 SET NULL → CASCADE로 변경.
    """
    bind = op.get_bind()
    inspector = inspect(bind)

    # 기존 FK 제약 조건 확인
    fks = inspector.get_foreign_keys('todo')
    parent_fk_name = None
    for fk in fks:
        if fk.get('constrained_columns') == ['parent_id']:
            parent_fk_name = fk.get('name')
            break

    with op.batch_alter_table('todo', schema=None) as batch_op:
        # 기존 FK 삭제
        if parent_fk_name:
            batch_op.drop_constraint(parent_fk_name, type_='foreignkey')

        # 기존 FK 복원: ondelete='CASCADE'
        batch_op.create_foreign_key(
            'fk_todo_parent_id',
            'todo',
            ['parent_id'],
            ['id'],
            ondelete='CASCADE'
        )
