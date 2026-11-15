"""raise allocated_duration of active timers to elapsed_time

RUNNING·PAUSED 타이머 중 elapsed_time이 allocated_duration을 넘는 행은
allocated_duration을 elapsed_time으로 올린다. COMPLETED·CANCELLED 행은 그대로 둔다.
다시 실행해도 결과가 같다.

회귀 테스트: tests/db/test_raise_allocated_duration_migration.py

Revision ID: 314620d41758
Revises: 561746fec396
Create Date: 2026-11-09 14:52:28.652276+09:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '314620d41758'
down_revision: Union[str, None] = '561746fec396'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text(
        "UPDATE timersession SET allocated_duration = elapsed_time"
        " WHERE elapsed_time > allocated_duration AND status IN ('RUNNING', 'PAUSED')"
    ))


def downgrade() -> None:
    """원래 allocated_duration을 남기지 않으므로 되돌리지 않는다 (버전 표시만 내려간다)"""
