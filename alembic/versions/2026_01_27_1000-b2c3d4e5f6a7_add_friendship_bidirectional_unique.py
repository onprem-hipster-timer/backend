"""add_friendship_bidirectional_unique_constraint

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-01-27 10:00:00.000000+09:00

이 마이그레이션은 friendship 테이블에 양방향 유니크 제약을 추가합니다.
A→B와 B→A가 동시에 존재할 수 없도록 보장합니다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. pair_user_id_1, pair_user_id_2 컬럼 추가 (nullable로 시작)
    op.add_column('friendship', sa.Column('pair_user_id_1', sa.String(), nullable=True))
    op.add_column('friendship', sa.Column('pair_user_id_2', sa.String(), nullable=True))
    
    # 2. 기존 데이터 backfill - 정렬된 페어 ID 계산
    # pair_user_id_1 = min(requester_id, addressee_id)
    # pair_user_id_2 = max(requester_id, addressee_id)
    connection = op.get_bind()
    
    # SQLite와 PostgreSQL 모두 지원하는 CASE 문 사용
    connection.execute(sa.text("""
        UPDATE friendship
        SET pair_user_id_1 = CASE 
                WHEN requester_id <= addressee_id THEN requester_id 
                ELSE addressee_id 
            END,
            pair_user_id_2 = CASE 
                WHEN requester_id <= addressee_id THEN addressee_id 
                ELSE requester_id 
            END
    """))
    
    # 3. 중복 레코드 정리 (동일 페어가 여러 개 있으면 하나만 남김)
    # 우선순위: BLOCKED > ACCEPTED > PENDING
    # 중복이 있으면 우선순위가 높은 것만 남기고 삭제
    
    # 중복 레코드 식별 및 삭제 (SQLite/PostgreSQL 호환)
    # 각 페어에서 가장 높은 우선순위의 레코드 ID를 찾고, 나머지 삭제
    try:
        # 중복 페어 찾기
        result = connection.execute(sa.text("""
            SELECT pair_user_id_1, pair_user_id_2, COUNT(*) as cnt
            FROM friendship
            GROUP BY pair_user_id_1, pair_user_id_2
            HAVING COUNT(*) > 1
        """))
        
        duplicates = result.fetchall()
        
        for dup in duplicates:
            pair_1, pair_2, _ = dup
            
            # 이 페어의 모든 레코드 조회 (우선순위 순으로 정렬)
            # blocked=0, accepted=1, pending=2 (낮은 값이 우선)
            rows = connection.execute(sa.text("""
                SELECT id, status FROM friendship
                WHERE pair_user_id_1 = :pair_1 AND pair_user_id_2 = :pair_2
                ORDER BY 
                    CASE status 
                        WHEN 'blocked' THEN 0 
                        WHEN 'accepted' THEN 1 
                        WHEN 'pending' THEN 2 
                        ELSE 3 
                    END,
                    created_at ASC
            """), {"pair_1": pair_1, "pair_2": pair_2}).fetchall()
            
            # 첫 번째(우선순위 가장 높은) 레코드를 제외하고 삭제
            if len(rows) > 1:
                keep_id = rows[0][0]
                for row in rows[1:]:
                    delete_id = row[0]
                    connection.execute(sa.text("""
                        DELETE FROM friendship WHERE id = :delete_id
                    """), {"delete_id": delete_id})
    except Exception:
        # 중복이 없거나 에러 발생 시 무시
        pass
    
    # 4. 양방향 유니크 제약 추가
    op.create_unique_constraint(
        'uq_friendship_bidirectional', 
        'friendship', 
        ['pair_user_id_1', 'pair_user_id_2']
    )


def downgrade() -> None:
    # 1. 유니크 제약 삭제
    op.drop_constraint('uq_friendship_bidirectional', 'friendship', type_='unique')
    
    # 2. 컬럼 삭제
    op.drop_column('friendship', 'pair_user_id_2')
    op.drop_column('friendship', 'pair_user_id_1')
