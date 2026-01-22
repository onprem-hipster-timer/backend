"""
Friendship 모델

사용자 간 친구 관계를 관리합니다.
양방향 관계를 단일 레코드로 표현하며, 요청/수락 워크플로우를 지원합니다.
"""
from enum import Enum
from typing import Optional

from sqlalchemy import Column, Enum as SQLEnum, UniqueConstraint, Index
from sqlmodel import Field

from app.models.base import UUIDBase, TimestampMixin


class FriendshipStatus(str, Enum):
    """친구 관계 상태"""
    PENDING = "pending"       # 요청 대기 중
    ACCEPTED = "accepted"     # 수락됨 (친구)
    BLOCKED = "blocked"       # 차단됨


class Friendship(UUIDBase, TimestampMixin, table=True):
    """
    친구 관계 모델
    
    - requester_id: 친구 요청을 보낸 사용자
    - addressee_id: 친구 요청을 받은 사용자
    - status: 관계 상태 (pending, accepted, blocked)
    
    Note: 양방향 관계이므로, 친구 조회 시 양쪽 모두 확인해야 함
    """
    __tablename__ = "friendship"
    
    # 요청자 (OIDC sub claim)
    requester_id: str = Field(index=True)
    
    # 수신자 (OIDC sub claim)
    addressee_id: str = Field(index=True)
    
    # 관계 상태
    status: FriendshipStatus = Field(
        default=FriendshipStatus.PENDING,
        sa_column=Column(
            SQLEnum(FriendshipStatus, native_enum=False, values_callable=lambda x: [e.value for e in x]),
            nullable=False,
            default=FriendshipStatus.PENDING.value,
        )
    )
    
    # 차단한 경우 차단한 사용자 ID (양방향 중 누가 차단했는지)
    blocked_by: Optional[str] = Field(default=None, nullable=True)
    
    __table_args__ = (
        # 동일한 사용자 쌍에 대해 중복 관계 방지
        UniqueConstraint("requester_id", "addressee_id", name="uq_friendship_pair"),
        # 친구 조회 성능 최적화
        Index("ix_friendship_status", "status"),
        Index("ix_friendship_addressee_status", "addressee_id", "status"),
    )
