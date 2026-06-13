"""
UserProfileService 단위 테스트

JIT 프로필 동기화(생성/갱신/idempotent), 친구코드 생성·유일성, 코드→sub 해석.
"""
from sqlmodel import select

from app.core.auth import CurrentUser
from app.domain.user.service import UserProfileService
from app.models.user_profile import UserProfile


def _user(sub: str, name: str | None = None, picture: str | None = None,
          iss: str | None = "https://idp.example", preferred: str | None = None,
          email: str | None = None, email_verified: bool = False) -> CurrentUser:
    claims: dict = {}
    if iss:
        claims["iss"] = iss
    if preferred:
        claims["preferred_username"] = preferred
    return CurrentUser(
        sub=sub, name=name, picture=picture,
        email=email, email_verified=email_verified, raw_claims=claims,
    )


class TestProfileSync:
    def test_creates_profile_from_claims(self, test_session):
        cu = _user("u1", name="Alice", picture="https://cdn/a.png", iss="https://idp")
        p = UserProfileService(test_session, cu).sync_from_current_user()

        assert p.sub == "u1"
        assert p.display_name == "Alice"
        assert p.avatar_url == "https://cdn/a.png"
        assert p.iss == "https://idp"
        assert p.friend_code  # 생성됨

    def test_no_email_column_persisted(self, test_session):
        """email은 신원으로 영속화하지 않는다 (컬럼 자체가 없어야 함)"""
        cu = _user("u-mail", name="X")
        p = UserProfileService(test_session, cu).sync_from_current_user()
        assert not hasattr(p, "email")

    def test_display_name_fallback_to_preferred_username(self, test_session):
        cu = _user("u2", name=None, preferred="bob123")
        p = UserProfileService(test_session, cu).sync_from_current_user()
        assert p.display_name == "bob123"

    def test_display_name_none_when_no_claims(self, test_session):
        cu = _user("u3", name=None)
        p = UserProfileService(test_session, cu).sync_from_current_user()
        assert p.display_name is None

    def test_idempotent_same_friend_code(self, test_session):
        svc = UserProfileService(test_session, _user("u4", name="Carol"))
        code1 = svc.sync_from_current_user().friend_code
        code2 = svc.sync_from_current_user().friend_code
        assert code1 == code2

        rows = test_session.exec(select(UserProfile).where(UserProfile.sub == "u4")).all()
        assert len(rows) == 1

    def test_updates_changed_display_name_keeps_code(self, test_session):
        first = UserProfileService(test_session, _user("u5", name="Old")).sync_from_current_user()
        code = first.friend_code
        updated = UserProfileService(test_session, _user("u5", name="New")).sync_from_current_user()
        assert updated.display_name == "New"
        assert updated.friend_code == code  # 코드는 불변

    def test_friend_code_unique_across_users(self, test_session):
        a = UserProfileService(test_session, _user("ua")).sync_from_current_user()
        b = UserProfileService(test_session, _user("ub")).sync_from_current_user()
        assert a.friend_code != b.friend_code


class TestResolveFriendCode:
    def test_resolve_existing_code(self, test_session):
        target = UserProfileService(test_session, _user("target", name="T")).sync_from_current_user()
        svc = UserProfileService(test_session, _user("caller"))
        assert svc.resolve_friend_code(target.friend_code) == "target"

    def test_resolve_unknown_code_returns_none(self, test_session):
        svc = UserProfileService(test_session, _user("caller"))
        assert svc.resolve_friend_code("nonexistent-code") is None

    def test_friend_code_is_deterministic_sha256(self, test_session):
        """friend_code = base64url(SHA256(sub)) — 결정적"""
        import base64
        import hashlib
        p = UserProfileService(test_session, _user("user-x")).sync_from_current_user()
        expected = base64.urlsafe_b64encode(
            hashlib.sha256(b"user-x").digest()
        ).decode().rstrip("=")
        assert p.friend_code == expected


class TestEmailHash:
    def test_email_hash_set_when_verified(self, test_session):
        p = UserProfileService(
            test_session, _user("u1", email="A@Example.com ", email_verified=True)
        ).sync_from_current_user()
        assert p.email_hash is not None

    def test_email_hash_none_when_unverified(self, test_session):
        p = UserProfileService(
            test_session, _user("u2", email="b@example.com", email_verified=False)
        ).sync_from_current_user()
        assert p.email_hash is None

    def test_email_hash_normalized_case_and_trim(self, test_session):
        """정규화(소문자·trim) 후 해시 → 대소문자/공백 차이 무시"""
        from app.domain.user.service import email_hash_for
        assert email_hash_for("A@Example.com ") == email_hash_for("a@example.com")

    def test_resolve_email_matches_verified(self, test_session):
        UserProfileService(
            test_session, _user("target", email="target@example.com", email_verified=True)
        ).sync_from_current_user()
        svc = UserProfileService(test_session, _user("caller"))
        assert svc.resolve_email("Target@Example.com") == "target"

    def test_resolve_email_unverified_not_matchable(self, test_session):
        UserProfileService(
            test_session, _user("target2", email="t2@example.com", email_verified=False)
        ).sync_from_current_user()
        svc = UserProfileService(test_session, _user("caller"))
        assert svc.resolve_email("t2@example.com") is None

    def test_email_hash_cleared_when_email_unverified_later(self, test_session):
        """검증 해제 시 email_hash가 None으로 갱신됨"""
        UserProfileService(
            test_session, _user("u3", email="u3@example.com", email_verified=True)
        ).sync_from_current_user()
        updated = UserProfileService(
            test_session, _user("u3", email="u3@example.com", email_verified=False)
        ).sync_from_current_user()
        assert updated.email_hash is None
