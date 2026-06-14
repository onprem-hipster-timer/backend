"""
UserProfile CRUD 함수

사용자 표시 프로필 데이터 접근 레이어.
"""
from sqlmodel import Session, select

from app.models.user_profile import UserProfile


def get_by_sub(session: Session, sub: str) -> UserProfile | None:
    """sub(PK)로 프로필 조회"""
    return session.get(UserProfile, sub)


def get_by_friend_code(session: Session, friend_code: str) -> UserProfile | None:
    """친구코드로 프로필 조회 (친추 대상 해석용)"""
    statement = select(UserProfile).where(UserProfile.friend_code == friend_code)
    return session.exec(statement).first()


def get_by_email_hash(session: Session, email_hash: str) -> UserProfile | None:
    """이메일 해시로 프로필 조회 (이메일 기반 친추 대상 해석용)"""
    statement = select(UserProfile).where(UserProfile.email_hash == email_hash)
    return session.exec(statement).first()


def get_profiles_by_subs(session: Session, subs: list[str]) -> dict[str, UserProfile]:
    """여러 sub의 프로필을 한 번에 조회 (N+1 방지). {sub: UserProfile} 반환"""
    if not subs:
        return {}
    statement = select(UserProfile).where(UserProfile.sub.in_(subs))
    return {p.sub: p for p in session.exec(statement).all()}


def create_profile(
        session: Session,
        sub: str,
        iss: str | None,
        display_name: str | None,
        avatar_url: str | None,
        friend_code: str,
        email_hash: str | None = None,
) -> UserProfile:
    """프로필 생성"""
    profile = UserProfile(
        sub=sub,
        iss=iss,
        display_name=display_name,
        avatar_url=avatar_url,
        friend_code=friend_code,
        email_hash=email_hash,
    )
    session.add(profile)
    session.flush()
    session.refresh(profile)
    return profile


def update_profile_if_changed(
        session: Session,
        profile: UserProfile,
        *,
        display_name: str | None,
        avatar_url: str | None,
        email_hash: str | None,
        iss: str | None,
        friend_code: str,
) -> bool:
    """desired 값과 다른 필드만 기록(write 증폭 방지).

    변경된 필드가 하나라도 있으면 flush하고 True를, 없으면 미기록 후 False를 반환한다.
    `updated_at`은 TimestampMixin의 onupdate가 자동 갱신한다.
    """
    changed = False
    for field, value in (
        ("display_name", display_name),
        ("avatar_url", avatar_url),
        ("email_hash", email_hash),
        ("iss", iss),
        ("friend_code", friend_code),
    ):
        if getattr(profile, field) != value:
            setattr(profile, field, value)
            changed = True
    if changed:
        session.add(profile)
        session.flush()
    return changed
