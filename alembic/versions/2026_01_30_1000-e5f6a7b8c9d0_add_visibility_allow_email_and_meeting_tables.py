"""add_visibility_allow_email_and_meeting_tables

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-01-30 10:00:00.000000+09:00

Visibility 시스템 확장 및 Meeting 일정 조율 테이블 추가:
- VisibilityAllowEmail 테이블 추가 (이메일/도메인 기반 접근 제어)
- Meeting, MeetingParticipant, MeetingTimeSlot 테이블 추가
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    # ### VisibilityAllowEmail 테이블 생성 ###
    if 'visibility_allow_email' not in tables:
        op.create_table(
            'visibility_allow_email',
            sa.Column('id', sa.Uuid(), nullable=False),
            sa.Column('visibility_id', sa.Uuid(), nullable=False),
            sa.Column('email', sa.String(), nullable=True),
            sa.Column('domain', sa.String(), nullable=True),
            sa.ForeignKeyConstraint(['visibility_id'], ['resource_visibility.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_visibility_allow_email_id'), 'visibility_allow_email', ['id'], unique=False)
        op.create_index(op.f('ix_visibility_allow_email_visibility_id'), 'visibility_allow_email', ['visibility_id'],
                        unique=False)
        op.create_index(op.f('ix_visibility_allow_email_email'), 'visibility_allow_email', ['email'], unique=False)
        op.create_index(op.f('ix_visibility_allow_email_domain'), 'visibility_allow_email', ['domain'], unique=False)
        op.create_index('ix_allow_email_domain', 'visibility_allow_email', ['domain'], unique=False)
        op.create_unique_constraint('uq_allow_email_entry', 'visibility_allow_email',
                                    ['visibility_id', 'email', 'domain'])

    # ### Meeting 테이블 생성 ###
    if 'meeting' not in tables:
        op.create_table(
            'meeting',
            sa.Column('id', sa.Uuid(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.Column('owner_id', sa.String(), nullable=False),
            sa.Column('title', sa.String(), nullable=False),
            sa.Column('description', sa.String(), nullable=True),
            sa.Column('start_date', sa.Date(), nullable=False),
            sa.Column('end_date', sa.Date(), nullable=False),
            sa.Column('available_days', sa.JSON(), nullable=False),
            sa.Column('start_time', sa.Time(), nullable=False),
            sa.Column('end_time', sa.Time(), nullable=False),
            sa.Column('time_slot_minutes', sa.Integer(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.CheckConstraint('start_date <= end_date', name='ck_meeting_date_range'),
            sa.CheckConstraint('start_time < end_time', name='ck_meeting_time_range'),
            sa.CheckConstraint('time_slot_minutes > 0', name='ck_meeting_time_slot'),
        )
        op.create_index(op.f('ix_meeting_id'), 'meeting', ['id'], unique=False)
        op.create_index(op.f('ix_meeting_owner_id'), 'meeting', ['owner_id'], unique=False)

    # ### MeetingParticipant 테이블 생성 ###
    if 'meeting_participant' not in tables:
        op.create_table(
            'meeting_participant',
            sa.Column('id', sa.Uuid(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.Column('meeting_id', sa.Uuid(), nullable=False),
            sa.Column('user_id', sa.String(), nullable=True),
            sa.Column('display_name', sa.String(), nullable=False),
            sa.ForeignKeyConstraint(['meeting_id'], ['meeting.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_meeting_participant_id'), 'meeting_participant', ['id'], unique=False)
        op.create_index(op.f('ix_meeting_participant_meeting_id'), 'meeting_participant', ['meeting_id'],
                        unique=False)
        op.create_index(op.f('ix_meeting_participant_user_id'), 'meeting_participant', ['user_id'], unique=False)

    # ### MeetingTimeSlot 테이블 생성 ###
    if 'meeting_time_slot' not in tables:
        op.create_table(
            'meeting_time_slot',
            sa.Column('id', sa.Uuid(), nullable=False),
            sa.Column('participant_id', sa.Uuid(), nullable=False),
            sa.Column('slot_date', sa.Date(), nullable=False),
            sa.Column('start_time', sa.Time(), nullable=False),
            sa.Column('end_time', sa.Time(), nullable=False),
            sa.ForeignKeyConstraint(['participant_id'], ['meeting_participant.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.CheckConstraint('start_time < end_time', name='ck_time_slot_range'),
        )
        op.create_index(op.f('ix_meeting_time_slot_id'), 'meeting_time_slot', ['id'], unique=False)
        op.create_index(op.f('ix_meeting_time_slot_participant_id'), 'meeting_time_slot', ['participant_id'],
                        unique=False)
        op.create_index(op.f('ix_meeting_time_slot_slot_date'), 'meeting_time_slot', ['slot_date'], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    # ### MeetingTimeSlot 테이블 삭제 ###
    if 'meeting_time_slot' in tables:
        try:
            op.drop_constraint('ck_time_slot_range', 'meeting_time_slot', type_='check')
        except Exception:
            pass
        try:
            op.drop_index(op.f('ix_meeting_time_slot_slot_date'), table_name='meeting_time_slot')
        except Exception:
            pass
        try:
            op.drop_index(op.f('ix_meeting_time_slot_participant_id'), table_name='meeting_time_slot')
        except Exception:
            pass
        try:
            op.drop_index(op.f('ix_meeting_time_slot_id'), table_name='meeting_time_slot')
        except Exception:
            pass
        op.drop_table('meeting_time_slot')

    # ### MeetingParticipant 테이블 삭제 ###
    if 'meeting_participant' in tables:
        try:
            op.drop_index(op.f('ix_meeting_participant_user_id'), table_name='meeting_participant')
        except Exception:
            pass
        try:
            op.drop_index(op.f('ix_meeting_participant_meeting_id'), table_name='meeting_participant')
        except Exception:
            pass
        try:
            op.drop_index(op.f('ix_meeting_participant_id'), table_name='meeting_participant')
        except Exception:
            pass
        op.drop_table('meeting_participant')

    # ### Meeting 테이블 삭제 ###
    if 'meeting' in tables:
        try:
            op.drop_constraint('ck_meeting_time_slot', 'meeting', type_='check')
        except Exception:
            pass
        try:
            op.drop_constraint('ck_meeting_time_range', 'meeting', type_='check')
        except Exception:
            pass
        try:
            op.drop_constraint('ck_meeting_date_range', 'meeting', type_='check')
        except Exception:
            pass
        try:
            op.drop_index(op.f('ix_meeting_owner_id'), table_name='meeting')
        except Exception:
            pass
        try:
            op.drop_index(op.f('ix_meeting_id'), table_name='meeting')
        except Exception:
            pass
        op.drop_table('meeting')

    # ### VisibilityAllowEmail 테이블 삭제 ###
    if 'visibility_allow_email' in tables:
        try:
            op.drop_constraint('uq_allow_email_entry', 'visibility_allow_email', type_='unique')
        except Exception:
            pass
        try:
            op.drop_index('ix_allow_email_domain', table_name='visibility_allow_email')
        except Exception:
            pass
        try:
            op.drop_index(op.f('ix_visibility_allow_email_domain'), table_name='visibility_allow_email')
        except Exception:
            pass
        try:
            op.drop_index(op.f('ix_visibility_allow_email_email'), table_name='visibility_allow_email')
        except Exception:
            pass
        try:
            op.drop_index(op.f('ix_visibility_allow_email_visibility_id'), table_name='visibility_allow_email')
        except Exception:
            pass
        try:
            op.drop_index(op.f('ix_visibility_allow_email_id'), table_name='visibility_allow_email')
        except Exception:
            pass
        op.drop_table('visibility_allow_email')
