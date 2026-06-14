"""
인증 미들웨어

토큰을 best-effort로 검증해 request.state.current_user를 사전 설정한다(거부하지 않음).
RateLimitMiddleware 등 라우팅 전 단계나 Depends에서 중복 검증 없이 재사용하기 위함.
실제 401 게이트는 get_current_user 의존성이 담당한다.
"""
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.auth.client import oidc_client
from app.core.auth.model import CurrentUser
from app.core.config import settings


class AuthMiddleware(BaseHTTPMiddleware):
    """
    인증 미들웨어 - request.state.current_user 설정

    토큰 검증 결과를 request.state에 저장하여
    다른 미들웨어(RateLimitMiddleware 등)나 Depends에서 중복 검증 없이 사용 가능

    처리 흐름:
    1. Authorization 헤더에서 Bearer 토큰 추출
    2. OIDC Provider를 통해 JWT 검증
    3. 검증 성공 시 request.state.current_user에 CurrentUser 저장
    4. 검증 실패/토큰 없음 시 request.state.current_user = None
    """

    async def dispatch(
            self,
            request: Request,
            call_next: RequestResponseEndpoint,
    ) -> Response:
        # 기본값 설정 (미인증 상태)
        request.state.current_user = None

        # OIDC 비활성화 시 테스트 사용자
        if not settings.OIDC_ENABLED:
            request.state.current_user = CurrentUser.mock()
            return await call_next(request)

        # Authorization 헤더 확인
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                claims = await oidc_client.verify_token(token)
                sub = claims.get("sub")
                if sub:
                    request.state.current_user = CurrentUser.from_claims(claims)
            except Exception:
                # 토큰 검증 실패 - 미인증 상태로 진행
                # 실제 인증 에러는 엔드포인트의 get_current_user에서 처리
                pass

        return await call_next(request)
