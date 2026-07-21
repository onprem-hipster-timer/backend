import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Type

from pydantic.experimental.missing_sentinel import MISSING
from sqlalchemy import Column, Enum as SAEnum, inspect
from sqlmodel import SQLModel, Field


def utc_now_naive() -> datetime:
    """UTC 현재 시간을 timezone-naive로 반환 (PostgreSQL TIMESTAMP WITHOUT TIME ZONE 호환)"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def str_enum_column(
        enum_cls: Type[Enum],
        *,
        default: Optional[Enum] = None,
        nullable: bool = False,
        index: bool = False,
) -> Column:
    """
    도메인 enum을 VARCHAR로 저장하는 표준 컬럼

    네이티브 DB enum(Postgres `CREATE TYPE`)은 값 추가마다 `ALTER TYPE`
    마이그레이션이 필요하고 SQLite와 이식성이 깨지므로 금지한다
    (`native_enum=False`). 저장 값은 멤버 이름이 아니라 `.value`다.
    정책 고정: tests/models/test_enum_columns.py

    :param enum_cls: (str, Enum) 도메인 enum 클래스
    :param default: 컬럼 기본값 (enum 멤버로 전달)
    """
    return Column(
        SAEnum(
            enum_cls,
            native_enum=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=nullable,
        index=index,
        default=default.value if default is not None else None,
    )


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


class UUIDBase(SQLModel, UpdateMixin):
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
    )
