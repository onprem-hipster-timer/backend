"""normalize visibility allow email

허용 이메일·도메인(visibility_allow_email.email, .domain)을 앞뒤 공백 없는 소문자로 바꾸고,
같은 접근권한 설정 안에서 바꾼 값이 같아진 행은 하나만 남긴다.
소문자 변환은 Python str.lower()로 해 DB 종류와 관계없이 API 입력 정규화와 같은 결과를 낸다.
다시 실행해도 결과가 같다.

회귀 테스트: tests/db/test_normalize_allow_email_migration.py

Revision ID: aeb221d93ba3
Revises: e7f3a9c5b1d8
Create Date: 2026-11-14 12:00:00.000000+09:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'aeb221d93ba3'
down_revision: Union[str, None] = 'e7f3a9c5b1d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_allow_email = sa.table(
    'visibility_allow_email',
    sa.column('id', sa.Uuid()),
    sa.column('visibility_id', sa.Uuid()),
    sa.column('email', sa.String()),
    sa.column('domain', sa.String()),
)


def _normalize(value: str | None) -> str | None:
    return value.strip().lower() if value is not None else None


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.select(_allow_email.c.id, _allow_email.c.visibility_id, _allow_email.c.email, _allow_email.c.domain)
        .order_by(_allow_email.c.id)
    ).all()

    seen: set[tuple] = set()
    duplicate_ids = []
    changed = []
    for row in rows:
        email, domain = _normalize(row.email), _normalize(row.domain)
        key = (row.visibility_id, email, domain)
        if key in seen:
            duplicate_ids.append(row.id)
            continue
        seen.add(key)
        if (email, domain) != (row.email, row.domain):
            changed.append((row.id, email, domain))

    if duplicate_ids:
        bind.execute(_allow_email.delete().where(_allow_email.c.id.in_(duplicate_ids)))
    for row_id, email, domain in changed:
        bind.execute(_allow_email.update().where(_allow_email.c.id == row_id).values(email=email, domain=domain))


def downgrade() -> None:
    """원래 대소문자와 지운 중복 행을 남기지 않으므로 되돌리지 않는다 (버전 표시만 내려간다)"""
