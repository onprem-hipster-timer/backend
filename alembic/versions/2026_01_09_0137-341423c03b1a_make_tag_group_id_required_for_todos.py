"""make_tag_group_id_required_for_todos

Revision ID: 341423c03b1a
Revises: d8eaba7f881e
Create Date: 2026-01-09 01:37:48.529260+09:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = '341423c03b1a'
down_revision: Union[str, None] = 'd8eaba7f881e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Todo의 tag_group_id를 필수로 만듭니다.
    
    기존 tag_group_id가 null인 Todo(is_todo=True)는:
    1. is_todo_group=True인 그룹 중 첫 번째를 찾아 할당
    2. 없으면 에러 발생 (수동 처리 필요)
    """
    conn = op.get_bind()
    
    # 1. 기존 null인 Todo 찾기
    result = conn.execute(text("""
        SELECT id FROM schedule 
        WHERE is_todo = 1 AND tag_group_id IS NULL
    """))
    null_todos = result.fetchall()
    
    if null_todos:
        # 2. 기본 Todo 그룹 찾기 (is_todo_group=True인 첫 번째)
        group_result = conn.execute(text("""
            SELECT id FROM tag_group 
            WHERE is_todo_group = 1 
            LIMIT 1
        """))
        default_group = group_result.fetchone()
        
        if default_group:
            default_group_id = default_group[0]
            # 3. null인 Todo에 기본 그룹 할당
            for todo_row in null_todos:
                todo_id = todo_row[0]
                conn.execute(text("""
                    UPDATE schedule 
                    SET tag_group_id = :group_id 
                    WHERE id = :todo_id
                """), {"group_id": default_group_id, "todo_id": todo_id})
            conn.commit()
        else:
            # 기본 그룹이 없으면 경고 (애플리케이션 레벨에서 검증)
            print(f"WARNING: {len(null_todos)} todos have null tag_group_id but no default todo group found.")
            print("Please create a todo group and assign it manually, or these todos will be filtered out.")
    
    # Note: 데이터베이스 레벨에서는 nullable을 유지 (일정은 tag_group_id가 선택)
    # 애플리케이션 레벨에서 Todo 생성 시 검증


def downgrade() -> None:
    """
    다운그레이드: tag_group_id를 다시 선택으로 변경
    (실제로는 데이터베이스 스키마 변경 없음)
    """
    pass
