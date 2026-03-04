# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Hipster Timer Project Contributors

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import api_router
from app.core.auth import AuthMiddleware
from app.core.config import settings
from app.core.error_handlers import register_exception_handlers
from app.core.logging import setup_logging
from app.db.session import init_db as init_db_sync, init_db_async  # 동기 및 비동기 방식
from app.domain.holiday.tasks import HolidayBackgroundTask
from app.middleware.request_logger import RequestLoggerMiddleware
from app.ratelimit.cloudflare import get_cloudflare_manager, get_trusted_proxy_manager
from app.ratelimit.middleware import RateLimitMiddleware

logger = logging.getLogger(__name__)

# 전역 태스크 참조 (shutdown 시 정리)
holiday_task = HolidayBackgroundTask()
_asyncio_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 라이프사이클 관리 (최신 권장 방식)
    
    yield 전: Startup
    yield 후: Shutdown
    
    이 패턴으로 startup/shutdown 로직 연결 가능
    """
    global _asyncio_task

    # ============ STARTUP ============
    logger.info("🌍 Starting FastAPI application")

    try:
        # 1. 로깅 설정
        setup_logging()

        # 2. Rate Limit status check
        if settings.RATE_LIMIT_ENABLED:
            logger.info("✅ Rate limiting is ENABLED")
        else:
            logger.warning("⚠️  Rate limiting is DISABLED")

        # 3. OIDC authentication status check
        if not settings.OIDC_ENABLED:
            logger.warning("")
            logger.warning("########################################################")
            logger.warning("#                                                      #")
            logger.warning("#   ⚠️  WARNING: OIDC authentication is DISABLED!      #")
            logger.warning("#                                                      #")
            logger.warning("#   All requests will use a mock test user:            #")
            logger.warning("#   - sub: test-user-id                                #")
            logger.warning("#   - email: test@example.com                          #")
            logger.warning("#                                                      #")
            logger.warning("#   Set OIDC_ENABLED=true for production!              #")
            logger.warning("#                                                      #")
            logger.warning("########################################################")
            logger.warning("")

        # 4. 동기 DB 초기화 (기존 코드 호환성)
        init_db_sync()
        logger.info("✅ Database tables initialized (sync)")

        # 5. 비동기 DB 초기화 (새로운 holiday 테이블)
        await init_db_async()
        logger.info("✅ Database tables initialized (async)")

        # 6. 공휴일 배경 태스크 시작
        _asyncio_task = asyncio.create_task(holiday_task.run())
        logger.info("✅ Holiday background task scheduled")

        # 7. Cloudflare/Trusted Proxy 설정 초기화
        if settings.CF_ENABLED:
            cf_manager = get_cloudflare_manager()
            success = await cf_manager.initialize()
            if success:
                logger.info("✅ Cloudflare IP list initialized")
            else:
                logger.warning("⚠️  Failed to fetch Cloudflare IPs, will use Fail-Safe mode")
        elif settings.trusted_proxy_ips:
            trusted_manager = get_trusted_proxy_manager()
            trusted_manager.initialize()
            logger.info(f"✅ Trusted proxy IPs configured: {len(settings.trusted_proxy_ips)} entries")
        else:
            logger.info("ℹ️  No proxy configuration (direct connection mode)")

    except Exception as e:
        logger.error(f"❌ Startup failed: {str(e)}", exc_info=True)
        raise

    # ============ APP 실행 중... ============
    yield

    # ============ SHUTDOWN ============
    logger.info("🛑 Shutting down FastAPI application")

    try:
        # 1. 백그라운드 태스크 정상 종료
        if _asyncio_task:
            holiday_task.is_running = False
            _asyncio_task.cancel()

            try:
                await _asyncio_task
            except asyncio.CancelledError:
                logger.info("✅ Holiday background task stopped")

    except Exception as e:
        logger.error(f"Error during shutdown: {str(e)}", exc_info=True)

    logger.info("✅ FastAPI application shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION if settings.ENVIRONMENT != "production" else None,
    lifespan=lifespan,
    # API 문서 설정 (빈 문자열이면 비활성화 - FastAPI 공식 문서 권장 방식)
    openapi_url=settings.OPENAPI_URL or None,
    docs_url=settings.DOCS_URL or None,
    redoc_url=settings.REDOC_URL or None,
)

# Exception Handler 등록
register_exception_handlers(app)

# CORS 설정 (환경변수로 주입 가능)
# 주의: allow_origins=["*"]와 allow_credentials=True는 호환되지 않음
# origin을 특정 도메인으로 설정해야 credentials를 True로 사용 가능
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.cors_methods,
    allow_headers=settings.cors_headers,
)

# Middleware 등록 (순서 중요: 아래에서 위로 실행됨 - 마지막 등록이 가장 먼저 실행)
# 1. Request Logger
app.add_middleware(RequestLoggerMiddleware)

# 2. Rate Limit - 인증된 사용자 정보(request.state.current_user)를 활용
# 항상 미들웨어 추가 (내부에서 settings.RATE_LIMIT_ENABLED 체크하여 비활성화 시 바로 통과)
# 조건부 추가 시 Python 모듈 캐싱으로 인해 테스트에서 동적 활성화가 불가능함
app.add_middleware(RateLimitMiddleware)

# 3. Auth - 가장 먼저 실행되어 request.state.current_user 설정
#    RateLimitMiddleware와 엔드포인트에서 중복 토큰 검증 없이 재사용
app.add_middleware(AuthMiddleware)

# API Router 등록 (REST + GraphQL + WebSocket 모두 포함)
app.include_router(api_router)


# Health Check 엔드포인트 (인증 불필요, 로드밸런서/컨테이너 오케스트레이션용)
@app.get("/health", tags=["Health"])
async def health_check():
    """
    애플리케이션 상태 확인
    
    로드밸런서, Kubernetes, ECS 등에서 사용하는 health check 엔드포인트.
    인증 없이 접근 가능합니다.
    """
    content: dict = {"status": "healthy"}
    if settings.ENVIRONMENT != "production":
        content["version"] = settings.APP_VERSION
        content["environment"] = settings.ENVIRONMENT
    return JSONResponse(status_code=200, content=content)
