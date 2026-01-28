"""change_timer_status_to_uppercase

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-01-29 02:18:00.000000+09:00

이 마이그레이션은 TimerSession 테이블의 status 컬럼 값을 소문자에서 대문자로 변경합니다.
- "running" -> "RUNNING"
- "paused" -> "PAUSED"
- "completed" -> "COMPLETED"
- "cancelled" -> "CANCELLED"
- "not_started" -> "NOT_STARTED"
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """status 값을 대문자로 변경"""
    connection = op.get_bind()
    
    # SQLite와 PostgreSQL 모두 지원하는 UPPER 함수 사용
    # 각 상태 값을 개별적으로 업데이트
    connection.execute(sa.text("""
        UPDATE timersession
        SET status = 'RUNNING'
        WHERE status = 'running'
    """))
    
    connection.execute(sa.text("""
        UPDATE timersession
        SET status = 'PAUSED'
        WHERE status = 'paused'
    """))
    
    connection.execute(sa.text("""
        UPDATE timersession
        SET status = 'COMPLETED'
        WHERE status = 'completed'
    """))
    
    connection.execute(sa.text("""
        UPDATE timersession
        SET status = 'CANCELLED'
        WHERE status = 'cancelled'
    """))
    
    connection.execute(sa.text("""
        UPDATE timersession
        SET status = 'NOT_STARTED'
        WHERE status = 'not_started'
    """))


def downgrade() -> None:
    """status 값을 소문자로 되돌림"""
    connection = op.get_bind()
    
    connection.execute(sa.text("""
        UPDATE timersession
        SET status = 'running'
        WHERE status = 'RUNNING'
    """))
    
    connection.execute(sa.text("""
        UPDATE timersession
        SET status = 'paused'
        WHERE status = 'PAUSED'
    """))
    
    connection.execute(sa.text("""
        UPDATE timersession
        SET status = 'completed'
        WHERE status = 'COMPLETED'
    """))
    
    connection.execute(sa.text("""
        UPDATE timersession
        SET status = 'cancelled'
        WHERE status = 'CANCELLED'
    """))
    
    connection.execute(sa.text("""
        UPDATE timersession
        SET status = 'not_started'
        WHERE status = 'NOT_STARTED'
    """))
