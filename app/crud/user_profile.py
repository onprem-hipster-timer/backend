"""
UserProfile CRUD 함수

사용자 표시 프로필 데이터 접근 레이어.
"""
from dataclasses import dataclass

from sqlmodel import Session, select

from app.models.user_profile import UserProfile


@dataclass(frozen=True)
class UserProfileSyncData:
    """JIT 동기화가 프로필에 반영할 값 묶음(내부 전용).

    외부 API 요청 body가 아니라 검증된 OIDC 클레임에서 파생되는 내부 projection이므로
    public DTO가 아닌 내부 dataclass로 둔다. `create_profile`/`update_profile_if_changed`
    공통 입력으로 쓰여 CRUD 시그니처를 단순화한다(`sub`는 PK라 update에선 무시).
    """
    sub: str
    iss: str | None
    display_name: str | None
    avatar_url: str | None
    friend_code: str
    verified_email: str | None


def get_by_sub(session: Session, sub: str) -> UserProfile | None:
    """sub(PK)로 프로필 조회"""
    return session.get(UserProfile, sub)


def get_by_friend_code(session: Session, friend_code: str) -> UserProfile | None:
    """친구코드로 프로필 조회 (친추 대상 해석용)"""
    statement = select(UserProfile).where(UserProfile.friend_code == friend_code)
    return session.exec(statement).first()


def get_by_verified_email(session: Session, verified_email: str) -> UserProfile | None:
    """검증 이메일로 프로필 조회 (이메일 기반 친추 대상 해석용)"""
    statement = select(UserProfile).where(UserProfile.verified_email == verified_email)
    return session.exec(statement).first()


def get_profiles_by_subs(session: Session, subs: list[str]) -> dict[str, UserProfile]:
    """여러 sub의 프로필을 한 번에 조회 (N+1 방지). {sub: UserProfile} 반환"""
    if not subs:
        return {}
    statement = select(UserProfile).where(UserProfile.sub.in_(subs))
    return {p.sub: p for p in session.exec(statement).all()}


def create_profile(session: Session, data: UserProfileSyncData) -> UserProfile:
    """프로필 생성"""
    profile = UserProfile(
        sub=data.sub,
        iss=data.iss,
        display_name=data.display_name,
        avatar_url=data.avatar_url,
        friend_code=data.friend_code,
        verified_email=data.verified_email,
    )
    session.add(profile)
    session.flush()
    session.refresh(profile)
    return profile


def update_profile_if_changed(
        session: Session,
        profile: UserProfile,
        data: UserProfileSyncData,
) -> bool:
    """desired 값(`data`)과 다른 필드만 기록(write 증폭 방지).

    `sub`는 PK라 갱신 대상이 아니다. 변경된 필드가 하나라도 있으면 flush하고 True를,
    없으면 미기록 후 False를 반환한다. `updated_at`은 TimestampMixin의 onupdate가 자동 갱신한다.
    """
    changed = False
    for field in ("display_name", "avatar_url", "verified_email", "iss", "friend_code"):
        value = getattr(data, field)
        if getattr(profile, field) != value:
            setattr(profile, field, value)
            changed = True
    if changed:
        session.add(profile)
        session.flush()
    return changed
