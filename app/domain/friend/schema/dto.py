"""
Friend Domain DTO (Data Transfer Objects)

친구 관련 데이터 전송 객체
"""
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import ConfigDict, field_validator, model_validator

from app.core.base_model import CustomModel
from app.models.friendship import FriendshipStatus


class FriendRequest(CustomModel):
    """친구 요청 DTO

    친추 대상을 `email` 또는 `friend_code` 중 **정확히 하나**로 지정한다:
    - `email`: 검증된 이메일 사용자와 매칭(항상 균일 202, 존재 비노출).
    - `friend_code`: `GET /v1/users/me`로 공유된 코드와 직접 매칭(미존재 404).

    둘 다 비었거나 둘 다 주어지면 422. `null`이라도 필드가 둘 다 있으면 422로 본다.
    `email`은 형식 검증된다. OIDC sub는 외부에서 얻을 수 없으므로 식별자로 받지 않는다.
    """
    email: str | None = None
    friend_code: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _exactly_one_target_field(cls, data: Any):
        """요청 바디에 email / friend_code 필드 중 정확히 하나만 존재하도록 강제."""
        if not isinstance(data, dict):
            return data

        provided_fields = [field for field in ("email", "friend_code") if field in data]
        if len(provided_fields) != 1:
            raise ValueError("email 또는 friend_code 중 정확히 하나를 제공해야 합니다")

        if data[provided_fields[0]] is None:
            raise ValueError("email 또는 friend_code는 null일 수 없습니다")
        return data

    @field_validator("friend_code")
    @classmethod
    def _friend_code_not_blank(cls, value: str | None) -> str | None:
        """빈 문자열 친구코드는 유효한 대상이 아니므로 422로 처리."""
        if value is None:
            return value
        stripped = value.strip()
        if not stripped:
            raise ValueError("friend_code는 비어 있을 수 없습니다")
        return stripped

    @field_validator("email")
    @classmethod
    def _email_format(cls, value: str | None) -> str | None:
        """추가 의존성 없이 친추 입력에 필요한 최소 이메일 형식을 검증."""
        if value is None:
            return value
        email = value.strip()
        if not email or any(ch.isspace() for ch in email):
            raise ValueError("email 형식이 올바르지 않습니다")
        local, sep, domain = email.partition("@")
        if not sep or "@" in domain or not local or not domain:
            raise ValueError("email 형식이 올바르지 않습니다")
        return email

    @property
    def is_email_target(self) -> bool:
        """이메일 경로 여부 (검증으로 정확히 하나가 보장됨)."""
        return self.email is not None


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
