"""PostgreSQL에서 회원의 약관 동의 기록과 파기가 겹칠 때

동의 기록(UserProfileService.record_consent)은 커밋할 때까지 프로필 행을 잠근다. 파기(purge_account)는 그 잠금이
풀린 뒤 동의를 함께 지우고, 파기가 먼저 프로필을 지웠으면 동의 기록은 AccountDeletedError다. 휴면 계정의 요청을
막는 라우트 규칙(DORMANT_ALLOWED_ROUTES)을 거치지 않고 서비스를 바로 부른다. SQLite는 행을 잠그지 않으므로
TEST_DATABASE_URL이 PostgreSQL일 때만 돈다. 한쪽 트랜잭션을 커밋 전에 멈춰 두고 다른 쪽을 시작한다.
"""
import asyncio
import os
import threading
from datetime import timedelta

import pytest
from sqlmodel import Session, select

import app.core.config as app_config
from app.crud import account_deletion as account_deletion_crud
from app.crud import user_profile as user_profile_crud
from app.domain.consent.schema.dto import ConsentCreate
from app.domain.user import purge
from app.domain.user.exceptions import AccountDeletedError
from app.domain.user.service import UserProfileService
from app.models import AccountDeletion, Consent, UserProfile
from app.models.base import utc_now_naive
from tests.conftest import make_user

_IS_POSTGRESQL = os.environ.get("TEST_DATABASE_URL", "").startswith("postgresql")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _IS_POSTGRESQL, reason="requires PostgreSQL via TEST_DATABASE_URL for row locks"),
]

# 멈춘 트랜잭션 뒤에서 다른 쪽이 시작해 겹치도록 두는 시간과, 어떤 기다림이든 넘지 않는 시간
HOLD_SECONDS = 1
BOUND_SECONDS = 30


@pytest.fixture
def released():
    """멈춘 트랜잭션을 놓는 신호. 테스트가 중간에 실패해도 끝에서 놓는다"""
    event = threading.Event()
    yield event
    event.set()


@pytest.fixture
def member(test_engine):
    """파기 대상인 회원 (유예 기간이 지난 탈퇴 신청, 현재 약관 버전에는 아직 동의하지 않았다)"""
    user = make_user("member")
    with Session(test_engine) as session:
        profile = UserProfileService(session, user).sync_from_current_user()
        user_profile_crud.set_deletion_requested_at(session, profile, utc_now_naive() - timedelta(days=1))
        session.commit()
    return user


def _record_consent(engine, user, before_commit=lambda: None) -> None:
    """PUT /v1/users/me/consent처럼 자기 세션에서 동의를 기록하고 커밋한다"""
    data = ConsentCreate(version=app_config.settings.CONSENT_VERSION, age_over_14=True, terms=True, privacy=True)
    with Session(engine) as session:
        UserProfileService(session, user).record_consent(data)
        before_commit()
        session.commit()


def _purge(engine, sub: str) -> bool:
    with Session(engine) as session:
        return purge.purge_account(session, sub, utc_now_naive())


async def _wait_until(event: threading.Event) -> None:
    assert await asyncio.to_thread(event.wait, BOUND_SECONDS)


def _assert_purged(engine, sub: str) -> None:
    with Session(engine) as session:
        assert session.exec(select(Consent).where(Consent.sub == sub)).all() == []
        assert session.get(UserProfile, sub) is None
        assert session.get(AccountDeletion, sub) is not None


@pytest.mark.asyncio
async def test_purge_started_during_open_consent_removes_it(test_engine, member, released):
    consent_written = threading.Event()

    def hold():
        consent_written.set()
        released.wait(BOUND_SECONDS)

    consent = asyncio.create_task(asyncio.to_thread(_record_consent, test_engine, member, hold))
    await _wait_until(consent_written)

    purged = asyncio.create_task(asyncio.to_thread(_purge, test_engine, member.sub))
    await asyncio.wait({purged}, timeout=HOLD_SECONDS)

    released.set()
    results = await asyncio.wait_for(asyncio.gather(consent, purged, return_exceptions=True), BOUND_SECONDS)

    _assert_purged(test_engine, member.sub)
    assert results == [None, True]


@pytest.mark.asyncio
async def test_consent_started_during_open_purge_is_refused(test_engine, member, monkeypatch, released):
    rows_deleted = threading.Event()
    add_deleted_account = account_deletion_crud.add_deleted_account

    def add_then_hold(session, sub, purged_at):
        add_deleted_account(session, sub, purged_at)
        rows_deleted.set()
        released.wait(BOUND_SECONDS)

    monkeypatch.setattr(account_deletion_crud, "add_deleted_account", add_then_hold)
    purged = asyncio.create_task(asyncio.to_thread(_purge, test_engine, member.sub))
    await _wait_until(rows_deleted)

    consent = asyncio.create_task(asyncio.to_thread(_record_consent, test_engine, member))
    await asyncio.wait({consent}, timeout=HOLD_SECONDS)

    released.set()
    purge_result, consent_result = await asyncio.wait_for(
        asyncio.gather(purged, consent, return_exceptions=True), BOUND_SECONDS
    )

    _assert_purged(test_engine, member.sub)
    assert purge_result is True
    assert isinstance(consent_result, AccountDeletedError)
