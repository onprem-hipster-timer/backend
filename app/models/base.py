import uuid
from datetime import datetime, timezone

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
    def apply_update(self, update_data: dict, exclude: list = None):
        """
        현재: exclude_unset=True로 만들어진 dict를 받아서 처리
        """
        mapper = inspect(self).mapper
        columns = mapper.column_attrs
        exclude = exclude or []

        for key, value in update_data.items():
            if key in exclude: continue
            if key not in columns: continue

            if value is None and not columns[key].nullable:
                continue

            setattr(self, key, value)

class UUIDBase(SQLModel,  UpdateMixin):
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
    )