"""
Friend Domain DTO (Data Transfer Objects)

친구 관련 데이터 전송 객체
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import ConfigDict

from app.core.base_model import CustomModel
from app.models.friendship import FriendshipStatus


class FriendRequest(CustomModel):
    """친구 요청 DTO"""
    addressee_id: str  # 친구 요청을 보낼 대상 사용자 ID


class FriendshipRead(CustomModel):
    """친구 관계 조회 DTO"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    requester_id: str
    addressee_id: str
    status: FriendshipStatus
    blocked_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class FriendRead(CustomModel):
    """친구 정보 조회 DTO (간략화)"""
    user_id: str  # 친구의 사용자 ID
    friendship_id: UUID  # 친구 관계 ID
    since: datetime  # 친구가 된 시점


class PendingRequestRead(CustomModel):
    """대기 중인 친구 요청 DTO"""
    id: UUID
    requester_id: str
    addressee_id: str
    created_at: datetime


class FriendshipActionResponse(CustomModel):
    """친구 관계 액션 응답 DTO"""
    success: bool
    message: str
    friendship: Optional[FriendshipRead] = None
