"""
인증 의존성 (FastAPI Dependency)

- get_current_user: 인증 게이트(실패 시 401). AuthMiddleware가 채운 request.state를 재사용.
- get_optional_current_user: 선택적 인증(미인증 허용 엔드포인트용).
- get_current_user_synced: 인증 + 최소 표시 프로필 JIT 동기화(인증 REST 라우터용).
"""
import logging

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from app.core.auth.client import oidc_client
from app.core.auth.model import CurrentUser
from app.core.config import settings
from app.db.session import get_db_transactional

logger = logging.getLogger(__name__)

# HTTP Bearer 스키마
security = HTTPBearer(auto_error=False)


async def get_current_user(
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> CurrentUser:
    """
    FastAPI Dependency: 현재 인증된 사용자 반환

    - AuthMiddleware에서 이미 검증된 경우 request.state에서 가져옴 (중복 검증 방지)
    - 그렇지 않으면 Authorization: Bearer <token> 헤더에서 토큰 추출 후 검증
    - CurrentUser 객체 반환

    OIDC_ENABLED=false인 경우 테스트용 mock 사용자 반환
    """
    # AuthMiddleware에서 이미 검증된 경우 재사용
    if hasattr(request.state, 'current_user') and request.state.current_user:
        return request.state.current_user

    # 인증 비활성화 시 테스트용 사용자 반환
    if not settings.OIDC_ENABLED:
        return CurrentUser.mock()

    # 토큰 없음
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 토큰 검증
    claims = await oidc_client.verify_token(credentials.credentials)

    # sub 클레임 필수
    sub = claims.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing 'sub' claim",
        )

    return CurrentUser.from_claims(claims)


async def get_optional_current_user(
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> CurrentUser | None:
    """
    FastAPI Dependency: 선택적 인증 (인증 없어도 접근 가능한 엔드포인트용)

    토큰이 없으면 None 반환, 토큰이 있으면 검증 후 CurrentUser 반환
    """
    # AuthMiddleware에서 이미 검증된 경우 재사용
    if hasattr(request.state, 'current_user') and request.state.current_user:
        return request.state.current_user

    if not settings.OIDC_ENABLED:
        return CurrentUser.mock()

    if not credentials:
        return None

    try:
        return await get_current_user(request, credentials)
    except HTTPException:
        return None


def get_current_user_synced(
        current_user: CurrentUser = Depends(get_current_user),
        session: Session = Depends(get_db_transactional),
) -> CurrentUser:
    """
    FastAPI Dependency: 인증된 사용자 반환 + 표시 프로필 JIT 동기화

    모든 인증 REST 라우터에 적용한다. 인증된 사용자의 표준 OIDC 클레임으로
    UserProfile을 upsert하여, 프론트가 별도 프로필 조회를 호출하지 않아도 친구 목록/
    받은 요청 표시정보와 이메일 친추 인덱스를 준비한다.

    - `get_db_transactional`은 요청 내 1회만 평가(FastAPI 캐시)되므로 엔드포인트와
      **동일 세션**을 공유하고 요청 끝에 함께 commit된다.
    - 동기화는 SAVEPOINT(begin_nested) 안에서 수행한다. 동기화가 실패해도 엔드포인트
      트랜잭션을 오염시키지 않고 best-effort로 넘어간다(표시정보는 None으로 degrade).
    """
    # 지연 import: domain.user.service가 app.core.auth.CurrentUser를 import하므로 순환 회피
    from app.domain.user.service import UserProfileService

    try:
        with session.begin_nested():
            UserProfileService(session, current_user).sync_from_current_user()
    except Exception as e:  # noqa: BLE001 - 동기화 실패는 요청을 막지 않는다
        logger.warning("User profile sync failed for sub=%s: %s", current_user.sub, e)

    return current_user
