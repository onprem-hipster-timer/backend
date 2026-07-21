"""add unique source_todo_id on schedule

'할일당 투영 일정은 정확히 1개' 불변조건을 DB가 최종 보장한다
(partial unique index — source_todo_id가 NULL이 아닌 행에만 적용).

구버전이 허용하던 레거시 링크를 먼저 정리한 뒤 인덱스를 만든다 —
정리 없이는 중복 링크가 있는 배포 DB에서 인덱스 생성이 실패한다:

1. 교차 소유 링크 해제 (일정 소유자 ≠ 할일 소유자)
2. 반복 일정 링크 해제 (반복 시리즈는 시점 마감의 투영이 아님)
3. 중복 링크 정리 (created_at, id 순 첫 행만 유지)
4. 연동 플래그 backfill — UNSCHEDULED/SCHEDULED는 링크 존재에서 파생,
   터미널 상태(DONE/CANCELLED)는 보존

회귀 테스트: tests/db/test_todo_schedule_migration.py

Revision ID: c4d7e8f1a2b3
Revises: b9e4d2a1c3f5
Create Date: 2026-07-20 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c4d7e8f1a2b3'
down_revision = 'b9e4d2a1c3f5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) 교차 소유 링크 해제 — 투영은 같은 소유자 안에서만 성립
    op.execute(sa.text("""
        UPDATE schedule SET source_todo_id = NULL
        WHERE source_todo_id IS NOT NULL
          AND owner_id != (
              SELECT todo.owner_id FROM todo WHERE todo.id = schedule.source_todo_id
          )
    """))

    # 2) 반복 일정 링크 해제 — 반복 시리즈는 시점 마감의 투영이 아님
    op.execute(sa.text("""
        UPDATE schedule SET source_todo_id = NULL
        WHERE source_todo_id IS NOT NULL
          AND recurrence_rule IS NOT NULL
    """))

    # 3) 중복 링크 정리 — 가장 먼저 만들어진 투영만 유지
    op.execute(sa.text("""
        UPDATE schedule SET source_todo_id = NULL
        WHERE id IN (
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY source_todo_id ORDER BY created_at, id
                ) AS rn
                FROM schedule
                WHERE source_todo_id IS NOT NULL
            ) ranked
            WHERE rn > 1
        )
    """))

    # 4) 연동 플래그 backfill — 링크 존재에서 파생, 터미널 상태는 보존
    op.execute(sa.text("""
        UPDATE todo SET status = 'SCHEDULED'
        WHERE status = 'UNSCHEDULED'
          AND EXISTS (
              SELECT 1 FROM schedule WHERE schedule.source_todo_id = todo.id
          )
    """))
    op.execute(sa.text("""
        UPDATE todo SET status = 'UNSCHEDULED'
        WHERE status = 'SCHEDULED'
          AND NOT EXISTS (
              SELECT 1 FROM schedule WHERE schedule.source_todo_id = todo.id
          )
    """))

    # 5) 이후의 중복은 DB가 차단
    op.create_index(
        "uq_schedule_source_todo_id",
        "schedule",
        ["source_todo_id"],
        unique=True,
        postgresql_where=sa.text("source_todo_id IS NOT NULL"),
        sqlite_where=sa.text("source_todo_id IS NOT NULL"),
    )


def downgrade() -> None:
    # 데이터 정리(1~4)는 되돌리지 않는다 — 정리 전 상태가 곧 결함이었으므로
    op.drop_index("uq_schedule_source_todo_id", table_name="schedule")
