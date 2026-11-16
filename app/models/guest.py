"""
Guest 모델

리소스 하나에 속한 게스트. 자격 증명은 Kratos identity에만 있고, 여기에는 identity와 리소스의 연결,
리소스 안에서 겹치지 않는 이름(정규형)을 둔다. 행이 없으면 그 identity는 로그인할 수 없고 게스트로 접근할 수 없다
(app/domain/guest).
"""
from uuid import UUID

from sqlalchemy import Column, Enum as SQLEnum, Index, UniqueConstraint
from sqlmodel import Field

from app.models.base import TimestampMixin, UUIDBase
from app.models.visibility import ResourceType


class Guest(UUIDBase, TimestampMixin, table=True):
    """게스트 (Kratos identity ↔ 리소스)"""
    __tablename__ = "guest"
    __table_args__ = (
        Index("ix_guest_resource", "resource_type", "resource_id"),
        UniqueConstraint("resource_type", "resource_id", "name", name="uq_guest_resource_name"),
    )

    # Kratos identity id (JWT sub)
    identity_id: str = Field(unique=True, index=True)

    resource_type: ResourceType = Field(
        sa_column=Column(
            SQLEnum(ResourceType, native_enum=False, values_callable=lambda x: [e.value for e in x]),
            nullable=False,
        )
    )
    # 리소스 ID (외래 키 없음 - 리소스 종류가 여럿이다)
    resource_id: UUID
    # 표시 이름의 정규형 (app/domain/guest/schema/dto.py normalize_guest_name). 리소스 안에서 겹치지 않는다
    name: str = Field(max_length=50)
