"""
인증 주체(Principal) 모델

검증된 JWT 클레임에서 추출한 현재 사용자. DB에 영속되지 않는 휘발성 값 객체이다.
(영속 표시 프로필은 app/models/user_profile.py의 UserProfile — 별개 개념.)
"""
from typing import Any

from pydantic import BaseModel


class CurrentUser(BaseModel):
    """현재 인증된 사용자 정보 (JWT 클레임에서 추출)"""
    sub: str  # 사용자 고유 식별자 (owner_id로 사용)
    email: str | None = None
    email_verified: bool = False  # OIDC `email_verified` (이메일 기반 친추 인덱싱 조건)
    name: str | None = None
    picture: str | None = None  # OIDC `picture` 클레임 (avatar_url 출처)

    # 추가 클레임 (필요시 확장)
    raw_claims: dict[str, Any] = {}

    @classmethod
    def from_claims(cls, claims: dict[str, Any]) -> "CurrentUser":
        """검증된 JWT 클레임에서 CurrentUser 생성 (표준 OIDC 클레임만 매핑).

        호출 전에 `sub` 존재를 보장해야 한다(클레임→객체 매핑의 단일 출처).
        """
        verified = claims.get("email_verified")
        return cls(
            sub=claims.get("sub"),
            email=claims.get("email"),
            email_verified=(verified is True or verified == "true"),
            name=claims.get("name"),
            picture=claims.get("picture"),
            raw_claims=claims,
        )

    @classmethod
    def mock(cls) -> "CurrentUser":
        """OIDC 비활성화(개발/테스트) 시 주입되는 mock 사용자 (단일 정의)."""
        return cls(
            sub="test-user-id",
            email="test@example.com",
            email_verified=True,
            name="Test User",
        )
