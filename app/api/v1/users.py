"""
Users Router

본인 표시 프로필 조회 API.

친구 추가는 검색이 아니라 **친구코드**로 한다(열거 표면 제거). 사용자는 여기서
자기 `friend_code`를 받아 친추 URL 등으로 공유하고, 상대는 그 코드로 친구 요청을
보낸다(POST /v1/friends/requests). 타인 프로필을 검색/조회하는 엔드포인트는 없다.

회원 탈퇴: 신청하면 휴면이 되어 다른 사용자에게 보이지 않고, 이 라우터의 조회·탈퇴 신청·취소 외
인증 요청은 403이다(app/core/auth/dependencies.py). ACCOUNT_DELETION_GRACE_DAYS가 지나면
POST /internal/accounts/purge가 파기한다. 테스트: tests/test_account_deletion_e2e.py
"""
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlmodel import Session

import app.core.config as app_config
from app.core import kratos_admin
from app.core.audit import log_account_access
from app.core.auth import CurrentUser, get_current_user
from app.db.session import CommittingSession, get_db_transactional
from app.domain.user.model import UserProfile
from app.domain.user.schema.dto import ConsentCreate, MyProfileRead
from app.domain.user.service import UserProfileService, deletion_scheduled_at

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=MyProfileRead)
async def get_my_profile(
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    본인 표시 프로필 조회 (없으면 토큰 클레임으로 생성).

    `friend_code`를 공유하면 상대가 그 코드로 친구 요청을 보낼 수 있다.
    """
    profile = UserProfileService(session, current_user).sync_from_current_user()
    return _to_read(profile)


@router.put("/me/consent", response_model=MyProfileRead)
async def put_my_consent(
        data: ConsentCreate,
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    만 14세 이상 확인, 이용약관, 개인정보처리방침 동의 기록.

    `version`은 응답 전에 받은 현재 약관 시행일이어야 한다(다르면 409).
    """
    profile = UserProfileService(session, current_user).record_consent(data.version)
    return _to_read(profile)


@router.post("/me/deletion", response_model=MyProfileRead)
async def request_my_deletion(
        request: Request,
        background_tasks: BackgroundTasks,
        session: Session = CommittingSession,
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    회원 탈퇴 신청. 계정이 휴면이 되고 `deletion_scheduled_at` 뒤 파기된다.

    다시 보내도 처음 신청 시각을 유지한다. 새로 신청하면 커밋 뒤 모든 기기의 로그인 세션을 끊는다.
    """
    profile, requested = UserProfileService(session, current_user).request_deletion()
    if requested:
        background_tasks.add_task(_after_deletion_requested, current_user.sub, _client_ip(request))
    return _to_read(profile)


@router.delete("/me/deletion", response_model=MyProfileRead)
async def cancel_my_deletion(
        request: Request,
        background_tasks: BackgroundTasks,
        session: Session = CommittingSession,
        current_user: CurrentUser = Depends(get_current_user),
):
    """회원 탈퇴 신청 취소. 신청하지 않았으면 아무것도 바꾸지 않는다."""
    profile, cancelled = UserProfileService(session, current_user).cancel_deletion()
    if cancelled:
        background_tasks.add_task(log_account_access, "deletion_cancelled", current_user.sub, _client_ip(request))
    return _to_read(profile)


async def _after_deletion_requested(sub: str, ip: str | None) -> None:
    log_account_access("deletion_requested", sub, ip)
    await kratos_admin.revoke_sessions(sub)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _to_read(profile: UserProfile) -> MyProfileRead:
    return MyProfileRead(
        id=profile.sub,
        display_name=profile.display_name,
        avatar_url=profile.avatar_url,
        friend_code=profile.friend_code,
        consent_version=app_config.settings.CONSENT_VERSION,
        consent_required=UserProfileService.consent_required(profile),
        deletion_requested_at=profile.deletion_requested_at,
        deletion_scheduled_at=deletion_scheduled_at(profile),
    )
