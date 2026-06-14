"""replace_user_profile_email_lookup_with_verified_email

Revision ID: b9e4d2a1c3f5
Revises: a7f3c1d9e2b4
Create Date: 2026-06-15 09:00:00.000000+09:00

Normalize older branch-local user_profile schemas to the current verified_email
column. Previous email_hash/email_lookup_key values were deterministic lookup
keys, not plaintext emails, so they cannot be migrated into verified_email.
Active users repopulate verified_email through JIT profile sync on their next
authenticated request.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = 'b9e4d2a1c3f5'
down_revision: Union[str, None] = 'a7f3c1d9e2b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    inspector = inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    inspector = inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    columns = _columns("user_profile")
    indexes = _indexes("user_profile")

    for index_name in (
        "ix_user_profile_email_hash",
        "ix_user_profile_email_lookup_key",
    ):
        if index_name in indexes:
            op.drop_index(op.f(index_name), table_name="user_profile")

    for column_name in ("email_hash", "email_lookup_key"):
        if column_name in columns:
            op.drop_column("user_profile", column_name)

    columns = _columns("user_profile")
    if "verified_email" not in columns:
        op.add_column("user_profile", sa.Column("verified_email", sa.String(), nullable=True))

    indexes = _indexes("user_profile")
    if "ix_user_profile_verified_email" not in indexes:
        op.create_index(
            op.f("ix_user_profile_verified_email"),
            "user_profile",
            ["verified_email"],
            unique=False,
        )


def downgrade() -> None:
    # This is a compatibility cleanup for branch-local schemas. The current
    # down revision already defines verified_email, so there is nothing to undo.
    pass
