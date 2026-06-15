"""
UserProfile Service

JIT(Just-In-Time) 프로필 동기화 및 친추 식별자(코드/이메일) 해석.

식별자 전략:
- friend_code = secrets.token_urlsafe(32) — 외부 공유용 무작위 코드. OIDC sub에서
  파생하지 않고 DB에 저장해 안정성을 유지한다.
- verified_email = normalize(email) — email_verified == true일 때만 저장한다.
  친구 추가 매칭용으로만 사용하고 API 응답/검색/목록에는 노출하지 않는다.

provider-agnostic 원칙: 출처는 이미 검증된 access token의 표준 OIDC 클레임뿐
(UserInfo·Admin API·provider SDK 호출 없음).
"""
import logging
import secrets

from sqlmodel import Session

from app.core.auth import CurrentUser
from app.crud import user_profile as crud
from app.domain.user.model import UserProfile

logger = logging.getLogger(__name__)


def generate_friend_code() -> str:
    """외부 공유용 URL-safe 무작위 친구코드 생성."""
    return secrets.token_urlsafe(32)


def verified_email_for(email: str) -> str:
    """친구 추가 매칭용 검증 이메일 정규화."""
    return email.strip().lower()


def _display_name_from_claims(current_user: CurrentUser) -> str | None:
    """표시명 폴백: name → preferred_username → None (email local-part는 미사용)."""
    if current_user.name:
        return current_user.name
    claims = current_user.raw_claims or {}
    return claims.get("preferred_username") or None


def _verified_email_from_claims(current_user: CurrentUser) -> str | None:
    """검증된(email_verified) 이메일이 있을 때만 verified_email 반환, 아니면 None."""
    if current_user.email and current_user.email_verified:
        return verified_email_for(current_user.email)
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
        verified_email = _verified_email_from_claims(cu)

        profile = crud.get_by_sub(self.session, cu.sub)
        if profile is None:
            profile = crud.create_profile(
                self.session,
                crud.UserProfileSyncData(
                    sub=cu.sub,
                    iss=iss,
                    display_name=display_name,
                    avatar_url=avatar_url,
                    friend_code=self._new_unique_friend_code(),
                    verified_email=verified_email,
                ),
            )
            logger.info(
                "Created user profile sub=%s (name=%s, picture=%s, email_indexed=%s)",
                cu.sub, display_name is not None, avatar_url is not None, verified_email is not None,
            )
            return profile

        # 변경 필드만 기록(write 증폭 방지)은 crud에 위임. 서비스는 "어떤 값을 동기화할지"만
        # 판단한다: iss는 클레임에 없으면 기존값 유지, friend_code는 비어있을 때만 무작위 백필.
        crud.update_profile_if_changed(
            self.session,
            profile,
            crud.UserProfileSyncData(
                sub=cu.sub,
                iss=iss or profile.iss,
                display_name=display_name,
                avatar_url=avatar_url,
                friend_code=profile.friend_code or self._new_unique_friend_code(),
                verified_email=verified_email,
            ),
        )
        return profile

    def _new_unique_friend_code(self) -> str:
        """충돌 가능성은 극히 낮지만 DB 조회로 방어한다."""
        while True:
            friend_code = generate_friend_code()
            if crud.get_by_friend_code(self.session, friend_code) is None:
                return friend_code

    def resolve_friend_code(self, friend_code: str) -> str | None:
        """친구코드 → sub 해석 (직접 매칭). 없으면 None."""
        profile = crud.get_by_friend_code(self.session, friend_code)
        return profile.sub if profile else None

    def resolve_email(self, email: str) -> str | None:
        """이메일 → sub 해석. 저장된 검증 이메일만 매칭. 없으면 None."""
        if not email:
            return None
        profile = crud.get_by_verified_email(self.session, verified_email_for(email))
        return profile.sub if profile else None
