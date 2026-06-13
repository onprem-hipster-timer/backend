"""
User Domain DTO

본인 표시 프로필 응답 객체. (타인 프로필을 임의 조회하는 DTO/엔드포인트는 없다 —
표시정보는 친구 목록/받은 요청 등 관계 성립/시도 상대에 한해서만 노출된다.)
"""
from typing import Optional

from app.core.base_model import CustomModel


class MyProfileRead(CustomModel):
    """본인 프로필 (GET /v1/users/me) — 친구코드 공유용"""
    id: str  # OIDC sub (본인 식별자)
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    friend_code: str  # 친추 URL에 실어 공유하는 불투명 코드
