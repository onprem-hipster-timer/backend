import uuid
from datetime import datetime, timezone

from sqlmodel import SQLModel, Field


def utc_now_naive() -> datetime:
    """UTC 현재 시간을 timezone-naive로 반환 (PostgreSQL TIMESTAMP WITHOUT TIME ZONE 호환)"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class UUIDBase(SQLModel):
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
    )


class TimestampMixin(SQLModel):
    created_at: datetime = Field(
        default_factory=utc_now_naive
    )
    updated_at: datetime = Field(
        default_factory=utc_now_naive,
        sa_column_kwargs={"onupdate": utc_now_naive},
    )
