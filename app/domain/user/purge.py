"""
회원 파기

탈퇴 신청 뒤 ACCOUNT_DELETION_GRACE_DAYS가 지난 계정을 지운다. 하루 한 번 실행한다
(POST /internal/accounts/purge).

1. 계정마다 한 트랜잭션: 프로필 행을 잠그고 아직 대상인지 다시 확인한 뒤 데이터를 지우고
   account_deletion에 sub를 남겨 커밋한다. 다른 실행이 먼저 지웠거나 취소했으면 건너뛴다
2. 커밋한 뒤 Kratos identity를 지운다. 실패하면 account_deletion에 남아 다음 실행이 다시 시도한다
3. 가입 뒤 UNVERIFIED_SIGNUP_RETENTION_HOURS가 지나도 이메일을 인증하지 않았고 서비스를 이용한 적 없는
   (프로필이 없는) Kratos identity를 지운다
4. Kratos identity를 지운 지 DELETED_ACCOUNT_RETENTION이 지난 기록은 지운다. 기록이 남아 있는 동안
   그 sub의 토큰은 401이고 프로필을 다시 만들지 않는다 (JWT 수명보다 길게 둔다)

친구에게 타이머 삭제 이벤트는 보내지 않는다. 휴면 동안 이미 보이지 않았다.
테스트: tests/test_account_purge_e2e.py, tests/test_unverified_signup_cleanup.py
"""
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

import app.core.config as app_config
from app.core import kratos_admin
from app.core.audit import log_account_access
from app.crud import account_deletion as crud
from app.crud.account_deletion import delete_user_data
from app.crud.user_profile import get_profiles_by_subs
from app.db.session import _session_manager
from app.models.base import utc_now_naive

logger = logging.getLogger(__name__)

DELETED_ACCOUNT_RETENTION = timedelta(days=1)


def purge_account(session: Session, sub: str, cutoff: datetime) -> bool:
    """cutoff 이전에 신청한 계정이면 지우고 커밋한다. 지웠으면 True."""
    try:
        profile = crud.get_purgeable_profile(session, sub, cutoff)
        if profile is None:
            session.rollback()
            return False
        delete_user_data(session, sub, profile.verified_email)
        crud.add_deleted_account(session, sub, utc_now_naive())
        session.commit()
    except IntegrityError:
        # 다른 실행이 같은 sub를 먼저 기록했다
        session.rollback()
        return False
    log_account_access("account_purged", sub, None)
    return True


def _purge_due_accounts_in_db() -> int:
    cutoff = utc_now_naive() - timedelta(days=app_config.settings.ACCOUNT_DELETION_GRACE_DAYS)
    with _session_manager.get_session() as session:
        subs = crud.get_purgeable_subs(session, cutoff)
    purged = 0
    for sub in subs:
        with _session_manager.get_session() as session:
            try:
                purged += purge_account(session, sub, cutoff)
            except Exception:
                session.rollback()
                logger.exception("계정 파기 실패")
    return purged


async def _delete_kratos_identities() -> int:
    """남은 Kratos identity를 지우고, 아직 남은 수를 돌려준다"""
    with _session_manager.get_session() as session:
        pending = crud.get_kratos_pending_subs(session)
    remaining = 0
    for sub in pending:
        if not await kratos_admin.delete_identity(sub):
            remaining += 1
            continue
        with _session_manager.get_session() as session:
            crud.mark_kratos_deleted(session, sub, utc_now_naive())
            session.commit()
    with _session_manager.get_session() as session:
        crud.delete_records_deleted_before(session, utc_now_naive() - DELETED_ACCOUNT_RETENTION)
        session.commit()
    return remaining


def _is_expired_unverified(identity: dict, cutoff: datetime) -> bool:
    addresses = identity.get("verifiable_addresses") or []
    if not addresses or any(a.get("verified") for a in addresses):
        return False
    created_at = datetime.fromisoformat(identity["created_at"].replace("Z", "+00:00"))
    return created_at.astimezone(UTC).replace(tzinfo=None) <= cutoff


async def _delete_unverified_signups() -> int:
    """기간이 지난 미인증 가입 identity를 지우고, 지운 수를 돌려준다"""
    from starlette.concurrency import run_in_threadpool

    identities = await kratos_admin.list_identities()
    if not identities:
        return 0
    cutoff = utc_now_naive() - timedelta(hours=app_config.settings.UNVERIFIED_SIGNUP_RETENTION_HOURS)
    candidates = [i["id"] for i in identities if _is_expired_unverified(i, cutoff)]
    if not candidates:
        return 0
    used = await run_in_threadpool(_subs_with_profile, candidates)
    removed = 0
    for identity_id in candidates:
        if identity_id in used:
            continue
        if await kratos_admin.delete_identity(identity_id):
            log_account_access("signup_expired", identity_id, None)
            removed += 1
    return removed


def _subs_with_profile(subs: list[str]) -> set[str]:
    with _session_manager.get_session() as session:
        return set(get_profiles_by_subs(session, subs))


async def purge_due_accounts() -> dict[str, int]:
    """파기 실행. 지운 계정 수, Kratos identity 삭제가 남은 계정 수, 지운 미인증 가입 수."""
    from starlette.concurrency import run_in_threadpool

    purged = await run_in_threadpool(_purge_due_accounts_in_db)
    kratos_pending = await _delete_kratos_identities()
    unverified_removed = await _delete_unverified_signups()
    return {"purged": purged, "kratos_pending": kratos_pending, "unverified_removed": unverified_removed}
