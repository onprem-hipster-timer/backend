import uuid
from datetime import datetime, timezone

from pydantic.experimental.missing_sentinel import MISSING
from sqlmodel import SQLModel, Field

from sqlalchemy import inspect


def utc_now_naive() -> datetime:
    """UTC 현재 시간을 timezone-naive로 반환 (PostgreSQL TIMESTAMP WITHOUT TIME ZONE 호환)"""
    return datetime.now(timezone.utc).replace(tzinfo=None)

class TimestampMixin(SQLModel):
    created_at: datetime = Field(
        default_factory=utc_now_naive
    )
    updated_at: datetime = Field(
        default_factory=utc_now_naive,
        sa_column_kwargs={"onupdate": utc_now_naive},
    )

class UpdateMixin:
    def apply_update(self, update_data: dict, exclude: list[str] | None = None):
        """
        MISSING sentinel을 사용하는 Update DTO의 model_dump()으로 만들어진 dict를 받아서 처리
        """
        mapper = inspect(self).mapper
        columns = mapper.column_attrs

        pk_fields = {attr.key for attr in columns if any(c.primary_key for c in attr.columns)}
        timestamp_fields = frozenset(TimestampMixin.__annotations__)
        excluded = pk_fields | timestamp_fields | {"owner_id"} | set(exclude or [])

        for key, value in update_data.items():
            if key in excluded: continue
            if key not in columns: continue

            if value is MISSING:
                continue

            if value is None and not columns[key].columns[0].nullable:
                continue

            setattr(self, key, value)

class UUIDBase(SQLModel,  UpdateMixin):
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
    )