"""
Rate Limit Middleware

FastAPI 미들웨어로 모든 /api/v1/* 요청에 레이트 리밋 적용
"""
import logging

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

from app.core import config as app_config
from app.ratelimit.cloudflare import get_real_client_ip
from app.ratelimit.config import get_rule_for_request
from app.ratelimit.limiter import get_limiter

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    레이트 리밋 미들웨어
    
    처리 흐름:
    1. 요청 경로가 /api/v1/*인지 확인
    2. 경로에 맞는 규칙 찾기
    3. 사용자 식별 (Authorization 헤더 -> sub 또는 Client IP)
    4. 레이트 리밋 체크
    5. 초과 시 429 응답, 허용 시 X-RateLimit-* 헤더 추가
    """

    async def dispatch(
            self,
            request: Request,
            call_next: RequestResponseEndpoint,
    ) -> Response:
        # 레이트 리밋 비활성화 시 바로 통과
        if not app_config.settings.RATE_LIMIT_ENABLED:
            return await call_next(request)

        path = request.url.path
        method = request.method

        # /v1/* 경로만 레이트 리밋 적용
        if not path.startswith("/v1"):
            return await call_next(request)

        # 규칙 찾기
        rule = get_rule_for_request(method, path)
        if not rule:
            # 매칭되는 규칙 없으면 레이트 리밋 미적용
            return await call_next(request)

        # 사용자 식별
        user_id = await self._get_user_id(request)

        # 레이트 리밋 체크
        limiter = get_limiter()
        result = await limiter.check_and_record(user_id, method, rule)

        if not result.allowed:
            # 429 Too Many Requests
            logger.warning(
                f"Rate limit exceeded: user={user_id}, path={path}, "
                f"count={result.current_count}/{result.max_requests}"
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요.",
                    "retry_after": result.reset_after,
                },
                headers={
                    "Retry-After": str(result.reset_after),
                    "X-RateLimit-Limit": str(result.max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(result.reset_after),
                },
            )

        # 요청 처리
        response = await call_next(request)

        # 응답에 레이트 리밋 헤더 추가
        response.headers["X-RateLimit-Limit"] = str(result.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(result.remaining)
        response.headers["X-RateLimit-Reset"] = str(result.reset_after)

        return response

    async def _get_user_id(self, request: Request) -> str:
        """
        사용자 식별자 추출
        
        우선순위:
        1. request.state.current_user (AuthMiddleware에서 설정됨 - 중복 검증 방지)
        2. Client IP 주소 (인증 없는 경우, 프록시 설정 고려)
        
        프록시 설정:
        - CF_ENABLED=True: Cloudflare IP 검증 후 CF-Connecting-IP 사용
        - TRUSTED_PROXY_IPS 설정: 해당 IP에서 오는 X-Forwarded-For 신뢰
        - 그 외: request.client.host 직접 사용
        """
        # AuthMiddleware에서 이미 검증된 사용자 정보 사용
        if hasattr(request.state, 'current_user') and request.state.current_user:
            return request.state.current_user.sub

        # 실제 클라이언트 IP 추출 (프록시 설정 고려)
        client_ip = await get_real_client_ip(
            request_client_host=request.client.host if request.client else None,
            cf_connecting_ip=request.headers.get("CF-Connecting-IP"),
            x_forwarded_for=request.headers.get("X-Forwarded-For"),
        )

        return f"ip:{client_ip}"
