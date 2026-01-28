"""add_pause_history_to_timer

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-01-28 10:00:00.000000+09:00

이 마이그레이션은 TimerSession 테이블에 pause_history JSONB 컬럼을 추가합니다.
일시정지/재개 이력을 저장하여 멀티 플랫폼 동기화 및 이력 추적을 지원합니다.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. pause_history JSON 컬럼 추가
    # SQLite에서는 JSON 타입을 TEXT로 저장, PostgreSQL에서는 JSONB 사용
    op.add_column('timersession', sa.Column(
        'pause_history',
        sa.JSON(),
        nullable=False,
        server_default='[]'
    ))

    # 2. 기존 paused_at 데이터를 pause_history로 마이그레이션
    # paused_at이 있는 레코드들은 pause 이력으로 변환
    connection = op.get_bind()

    # 현재 paused_at이 있는 PAUSED 상태의 타이머들 조회
    result = connection.execute(sa.text("""
        SELECT id, paused_at, started_at, elapsed_time
        FROM timersession
        WHERE paused_at IS NOT NULL
    """))

    rows = result.fetchall()

    for row in rows:
        timer_id, paused_at, started_at, elapsed_time = row

        # pause_history 생성: start 이벤트 + pause 이벤트
        history = []

        if started_at:
            history.append({
                "action": "start",
                "at": started_at.isoformat() if hasattr(started_at, 'isoformat') else str(started_at)
            })

        if paused_at:
            history.append({
                "action": "pause",
                "at": paused_at.isoformat() if hasattr(paused_at, 'isoformat') else str(paused_at),
                "elapsed": elapsed_time or 0
            })

        # JSON 문자열로 변환
        import json
        history_json = json.dumps(history)

        # 업데이트
        connection.execute(sa.text("""
            UPDATE timersession
            SET pause_history = :history
            WHERE id = :id
        """), {"history": history_json, "id": timer_id})

    # 3. server_default 제거 (마이그레이션 완료 후)
    # SQLite에서는 batch mode 필요
    with op.batch_alter_table('timersession', schema=None) as batch_op:
        batch_op.alter_column('pause_history',
                              server_default=None)


def downgrade() -> None:
    # pause_history 컬럼 삭제
    op.drop_column('timersession', 'pause_history')
