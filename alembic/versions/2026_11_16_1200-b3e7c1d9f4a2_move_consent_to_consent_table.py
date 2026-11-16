"""move consent to consent table

약관 동의 기록을 user_profile 컬럼(consent_version, consented_at)에서 consent 테이블((sub, version)마다 한 행)로 옮긴다.
회원과 게스트가 같은 키(Kratos identity id)를 쓴다.

- upgrade: consent를 만들고(앱 시작의 create_all이 먼저 만들었으면 그대로 쓴다) consent_version이 있는 프로필을 옮긴 뒤
  두 컬럼을 지운다. consent에 같은 (sub, version)이 이미 있으면 그 행을 둔다
- downgrade: 두 컬럼을 되살려 sub마다 가장 나중에 동의한 행으로 채우고 consent를 지운다. 프로필이 없는 sub(게스트)의
  동의는 남지 않는다

회귀 테스트: tests/db/test_consent_migration.py

Revision ID: b3e7c1d9f4a2
Revises: f2b6d8a4c3e7
Create Date: 2026-11-16 12:00:00.000000+09:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'b3e7c1d9f4a2'
down_revision: Union[str, None] = 'f2b6d8a4c3e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_profile = sa.table(
    'user_profile',
    sa.column('sub', sa.String()),
    sa.column('consent_version', sa.String()),
    sa.column('consented_at', sa.DateTime()),
)
_consent = sa.table(
    'consent',
    sa.column('sub', sa.String()),
    sa.column('version', sa.String()),
    sa.column('consented_at', sa.DateTime()),
)


def _profile_columns() -> set[str]:
    return {c['name'] for c in sa.inspect(op.get_bind()).get_columns('user_profile')}


def upgrade() -> None:
    if 'consent' not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            'consent',
            sa.Column('sub', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('version', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('consented_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('sub', 'version'),
        )
    if 'consent_version' not in _profile_columns():
        return

    existing = _consent.alias('existing')
    already = sa.select(existing.c.sub).where(
        existing.c.sub == _profile.c.sub, existing.c.version == _profile.c.consent_version
    )
    op.get_bind().execute(
        _consent.insert().from_select(
            ['sub', 'version', 'consented_at'],
            sa.select(_profile.c.sub, _profile.c.consent_version, _profile.c.consented_at)
            .where(_profile.c.consent_version.is_not(None))
            .where(~sa.exists(already)),
        )
    )
    with op.batch_alter_table('user_profile') as batch_op:
        batch_op.drop_column('consented_at')
        batch_op.drop_column('consent_version')


def _latest(column: sa.ColumnElement) -> sa.ScalarSelect:
    """user_profile 행의 sub가 가장 나중에 동의한 consent 행의 column"""
    return (
        sa.select(column)
        .where(_consent.c.sub == _profile.c.sub)
        .order_by(_consent.c.consented_at.desc(), _consent.c.version.desc())
        .limit(1)
        .scalar_subquery()
    )


def downgrade() -> None:
    with op.batch_alter_table('user_profile') as batch_op:
        batch_op.add_column(sa.Column('consent_version', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column('consented_at', sa.DateTime(), nullable=True))
    op.get_bind().execute(
        _profile.update().values(
            consent_version=_latest(_consent.c.version),
            consented_at=_latest(_consent.c.consented_at),
        )
    )
    op.drop_table('consent')
