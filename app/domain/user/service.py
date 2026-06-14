"""
UserProfile Service

JIT(Just-In-Time) 프로필 동기화 및 친추 식별자(코드/이메일) 해석.

해싱 전략 (평문 SHA-256, 키 없음):
- friend_code = base64url(SHA256(sub)) — sub는 고엔트로피(UUID)라 사전공격 불가 →
  평문 해시로도 안전하며, 결정적이라 프로필 재생성에도 동일한 코드가 유지된다.
- email_hash = base64url(SHA256(normalize(email))) — email_verified == true일 때만.
  평문 email은 저장하지 않고 동일 입력의 해시와 매칭하는 용도로만 쓴다.

provider-agnostic 원칙: 출처는 이미 검증된 access token의 표준 OIDC 클레임뿐
(UserInfo·Admin API·provider SDK 호출 없음).
"""
import base64
import hashlib
import logging

from sqlmodel import Session

from app.core.auth import CurrentUser
from app.crud import user_profile as crud
from app.domain.user.model import UserProfile

logger = logging.getLogger(__name__)


def _sha256_b64(value: str) -> str:
    """base64url(SHA256(value)) — 패딩 제거(43자)."""
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def friend_code_for(sub: str) -> str:
    """sub로부터 결정적 친구코드 생성."""
    return _sha256_b64(sub)


def email_hash_for(email: str) -> str:
    """이메일 정규화(소문자·trim) 후 매칭용 해시 생성."""
    return _sha256_b64(email.strip().lower())


def _display_name_from_claims(current_user: CurrentUser) -> str | None:
    """표시명 폴백: name → preferred_username → None (email local-part는 미사용)."""
    if current_user.name:
        return current_user.name
    claims = current_user.raw_claims or {}
    return claims.get("preferred_username") or None


def _email_hash_from_claims(current_user: CurrentUser) -> str | None:
    """검증된(email_verified) 이메일이 있을 때만 email_hash 반환, 아니면 None."""
    if current_user.email and current_user.email_verified:
        return email_hash_for(current_user.email)
    return None


class UserProfileService:
    """사용자 표시 프로필 비즈니스 로직"""

    def __init__(self, session: Session, current_user: CurrentUser):
        self.session = session
        self.current_user = current_user

    def sync_from_current_user(self) -> UserProfile:
        """
        현재 인증된 사용자의 표준 OIDC 클레임으로 프로필을 upsert.

        write 증폭 방지: PK 조회 후 **신규이거나 값이 바뀐 경우에만** 기록.
        (전역 in-memory 상태 없이 idempotent — 테스트 격리 안전)
        """
        cu = self.current_user
        claims = cu.raw_claims or {}
        iss = claims.get("iss")
        display_name = _display_name_from_claims(cu)
        avatar_url = cu.picture
        email_hash = _email_hash_from_claims(cu)

        profile = crud.get_by_sub(self.session, cu.sub)
        if profile is None:
            profile = crud.create_profile(
                self.session,
                sub=cu.sub,
                iss=iss,
                display_name=display_name,
                avatar_url=avatar_url,
                friend_code=friend_code_for(cu.sub),
                email_hash=email_hash,
            )
            logger.info(
                "Created user profile sub=%s (name=%s, picture=%s, email_indexed=%s)",
                cu.sub, display_name is not None, avatar_url is not None, email_hash is not None,
            )
            return profile

        # 변경 필드만 기록(write 증폭 방지)은 crud에 위임. 서비스는 "어떤 값을 동기화할지"만
        # 판단한다: iss는 클레임에 없으면 기존값 유지, friend_code는 결정적이라 비어있을 때만 백필.
        crud.update_profile_if_changed(
            self.session,
            profile,
            display_name=display_name,
            avatar_url=avatar_url,
            email_hash=email_hash,
            iss=iss or profile.iss,
            friend_code=profile.friend_code or friend_code_for(cu.sub),
        )
        return profile

    def resolve_friend_code(self, friend_code: str) -> str | None:
        """친구코드 → sub 해석 (직접 매칭). 없으면 None."""
        profile = crud.get_by_friend_code(self.session, friend_code)
        return profile.sub if profile else None

    def resolve_email(self, email: str) -> str | None:
        """이메일 → sub 해석 (SHA256 매칭). 인덱싱된 검증 이메일만 매칭. 없으면 None."""
        if not email:
            return None
        profile = crud.get_by_email_hash(self.session, email_hash_for(email))
        return profile.sub if profile else None
