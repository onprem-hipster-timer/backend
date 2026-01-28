"""add_friendship_and_visibility_tables

Revision ID: a1b2c3d4e5f6
Revises: 62a5cb5aae21
Create Date: 2026-01-23 12:00:00.000000+09:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '62a5cb5aae21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    # ### Friendship 테이블 생성 ###
    if 'friendship' not in tables:
        op.create_table(
            'friendship',
            sa.Column('id', sa.Uuid(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.Column('requester_id', sa.String(), nullable=False),
            sa.Column('addressee_id', sa.String(), nullable=False),
            sa.Column('status', sa.String(), nullable=False),
            sa.Column('blocked_by', sa.String(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_friendship_id'), 'friendship', ['id'], unique=False)
        op.create_index(op.f('ix_friendship_requester_id'), 'friendship', ['requester_id'], unique=False)
        op.create_index(op.f('ix_friendship_addressee_id'), 'friendship', ['addressee_id'], unique=False)
        op.create_index('ix_friendship_status', 'friendship', ['status'], unique=False)
        op.create_index('ix_friendship_addressee_status', 'friendship', ['addressee_id', 'status'], unique=False)
        op.create_unique_constraint('uq_friendship_pair', 'friendship', ['requester_id', 'addressee_id'])

    # ### ResourceVisibility 테이블 생성 ###
    if 'resource_visibility' not in tables:
        op.create_table(
            'resource_visibility',
            sa.Column('id', sa.Uuid(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.Column('resource_type', sa.String(), nullable=False),
            sa.Column('resource_id', sa.Uuid(), nullable=False),
            sa.Column('owner_id', sa.String(), nullable=False),
            sa.Column('level', sa.String(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_resource_visibility_id'), 'resource_visibility', ['id'], unique=False)
        op.create_index(op.f('ix_resource_visibility_resource_id'), 'resource_visibility', ['resource_id'], unique=False)
        op.create_index(op.f('ix_resource_visibility_owner_id'), 'resource_visibility', ['owner_id'], unique=False)
        op.create_index('ix_visibility_resource', 'resource_visibility', ['resource_type', 'resource_id'], unique=False)
        op.create_index('ix_visibility_owner_type', 'resource_visibility', ['owner_id', 'resource_type'], unique=False)
        op.create_unique_constraint('uq_resource_visibility', 'resource_visibility', ['resource_type', 'resource_id'])

    # ### VisibilityAllowList 테이블 생성 ###
    if 'visibility_allow_list' not in tables:
        op.create_table(
            'visibility_allow_list',
            sa.Column('id', sa.Uuid(), nullable=False),
            sa.Column('visibility_id', sa.Uuid(), nullable=False),
            sa.Column('allowed_user_id', sa.String(), nullable=False),
            sa.ForeignKeyConstraint(['visibility_id'], ['resource_visibility.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_visibility_allow_list_id'), 'visibility_allow_list', ['id'], unique=False)
        op.create_index(op.f('ix_visibility_allow_list_visibility_id'), 'visibility_allow_list', ['visibility_id'],
                        unique=False)
        op.create_index(op.f('ix_visibility_allow_list_allowed_user_id'), 'visibility_allow_list', ['allowed_user_id'],
                        unique=False)
        op.create_unique_constraint('uq_allow_list_entry', 'visibility_allow_list', ['visibility_id', 'allowed_user_id'])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    # ### VisibilityAllowList 테이블 삭제 ###
    if 'visibility_allow_list' in tables:
        try:
            op.drop_constraint('uq_allow_list_entry', 'visibility_allow_list', type_='unique')
        except Exception:
            pass
        try:
            op.drop_index(op.f('ix_visibility_allow_list_allowed_user_id'), table_name='visibility_allow_list')
        except Exception:
            pass
        try:
            op.drop_index(op.f('ix_visibility_allow_list_visibility_id'), table_name='visibility_allow_list')
        except Exception:
            pass
        try:
            op.drop_index(op.f('ix_visibility_allow_list_id'), table_name='visibility_allow_list')
        except Exception:
            pass
        op.drop_table('visibility_allow_list')

    # ### ResourceVisibility 테이블 삭제 ###
    if 'resource_visibility' in tables:
        try:
            op.drop_constraint('uq_resource_visibility', 'resource_visibility', type_='unique')
        except Exception:
            pass
        try:
            op.drop_index('ix_visibility_owner_type', table_name='resource_visibility')
        except Exception:
            pass
        try:
            op.drop_index('ix_visibility_resource', table_name='resource_visibility')
        except Exception:
            pass
        try:
            op.drop_index(op.f('ix_resource_visibility_owner_id'), table_name='resource_visibility')
        except Exception:
            pass
        try:
            op.drop_index(op.f('ix_resource_visibility_resource_id'), table_name='resource_visibility')
        except Exception:
            pass
        try:
            op.drop_index(op.f('ix_resource_visibility_id'), table_name='resource_visibility')
        except Exception:
            pass
        op.drop_table('resource_visibility')

    # ### Friendship 테이블 삭제 ###
    if 'friendship' in tables:
        try:
            op.drop_constraint('uq_friendship_pair', 'friendship', type_='unique')
        except Exception:
            pass
        try:
            op.drop_index('ix_friendship_addressee_status', table_name='friendship')
        except Exception:
            pass
        try:
            op.drop_index('ix_friendship_status', table_name='friendship')
        except Exception:
            pass
        try:
            op.drop_index(op.f('ix_friendship_addressee_id'), table_name='friendship')
        except Exception:
            pass
        try:
            op.drop_index(op.f('ix_friendship_requester_id'), table_name='friendship')
        except Exception:
            pass
        try:
            op.drop_index(op.f('ix_friendship_id'), table_name='friendship')
        except Exception:
            pass
        op.drop_table('friendship')
