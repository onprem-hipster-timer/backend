"""
UserProfile 모델

OIDC sub ↔ 표시 정보(display_name, avatar_url) 매핑.

이 백엔드는 순수 OIDC Resource Server이므로 사용자 정체성은 매 요청의 JWT
클레임에서만 나온다. 친구 목록/받은 요청에서 "누가"를 표시하려면 타인의 표시
정보가 필요하지만, 그 정보의 유일한 출처는 각 사용자가 인증할 때의 토큰이다.
이 테이블은 인증된 사용자의 표준 OIDC 클레임을 JIT(Just-In-Time)로 캐싱한다.

설계 불변식:
- `sub`가 정본 키. 코드베이스 전체(friendship 등)가 sub 기반이라 자연 조인된다.
- 표시 필드(display_name/avatar_url)는 **서명된 JWT 클레임에서만** 채운다.
  사용자가 임의로 쓰는 경로가 없으므로 위변조 표면이 없다.
- **email은 저장하지 않는다.** email은 ALLOWED_EMAILS 접근제어에서 요청자 본인
  토큰으로만 라이브 매칭되며, 신원으로 영속화/노출하지 않는다.
- 외부 공유는 `sub`가 아니라 `friend_code`로만 한다(OIDC subject 비노출).
"""
from sqlmodel import Field

from app.models.base import TimestampMixin


class UserProfile(TimestampMixin, table=True):
    """
    사용자 표시 프로필 (JIT 캐시)

    - sub: OIDC subject (PK, 정본 식별자)
    - iss: OIDC issuer (부가 식별·감사용; 전역 유일키는 iss+sub)
    - display_name: 표시명 (OIDC `name` 클레임, 없으면 None)
    - avatar_url: 아바타 URL (OIDC `picture` 클레임, 없으면 None)
    - friend_code: 친구 추가용 불투명 코드 (외부 공유 식별자, unique)
    """
    __tablename__ = "user_profile"

    sub: str = Field(primary_key=True)
    iss: str | None = Field(default=None, nullable=True)
    display_name: str | None = Field(default=None, nullable=True)
    avatar_url: str | None = Field(default=None, nullable=True)
    # 친추용 식별자 = base64url(SHA256(sub)). 결정적·안정적, sub는 고엔트로피라 평문 해시 안전.
    friend_code: str = Field(index=True, unique=True)
    # 이메일 기반 친추용 = base64url(SHA256(normalize(email))). 검증된 이메일이 있을 때만 채워짐.
    # 평문 이메일은 저장하지 않고, 동일 이메일 입력의 해시와 매칭하는 용도로만 쓴다.
    email_hash: str | None = Field(default=None, nullable=True, index=True)
