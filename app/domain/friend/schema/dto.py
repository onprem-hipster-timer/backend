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
    """친구 요청 DTO

    친추 대상을 단일 `identifier`로 지정한다(라우터에서 `@` 유무로 분기):
    - `@` 포함 → 이메일. 검증된 이메일 사용자와 매칭(항상 균일 202, 존재 비노출).
    - `@` 없음 → 친구코드. `GET /v1/users/me`로 공유된 값과 직접 매칭(미존재 404).
    OIDC sub는 외부에서 얻을 수 없으므로 식별자로 받지 않는다.
    """
    identifier: str  # 이메일 또는 친구코드


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
    display_name: Optional[str] = None  # 친구 표시명 (프로필 없으면 None)
    avatar_url: Optional[str] = None  # 친구 아바타 URL (프로필 없으면 None)
    since: datetime  # 친구가 된 시점


class PendingRequestRead(CustomModel):
    """대기 중인 친구 요청 DTO

    받은 요청에서 requester_* 필드로 "누가 보냈는지"를 표시한다.
    (보낸 요청에서는 requester가 본인이므로 본인 정보가 채워진다.)
    """
    id: UUID
    requester_id: str
    addressee_id: str
    requester_display_name: Optional[str] = None
    requester_avatar_url: Optional[str] = None
    created_at: datetime


class FriendshipActionResponse(CustomModel):
    """친구 관계 액션 응답 DTO"""
    success: bool
    message: str
    friendship: Optional[FriendshipRead] = None
