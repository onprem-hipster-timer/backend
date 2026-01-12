import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import settings
from app.core.error_handlers import register_exception_handlers
from app.core.logging import setup_logging
from app.db.session import init_db as init_db_sync, init_db_async  # 동기 및 비동기 방식
from app.domain.holiday.tasks import HolidayBackgroundTask
from app.middleware.request_logger import RequestLoggerMiddleware

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

        # 2. OIDC authentication status check
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

        # 3. 동기 DB 초기화 (기존 코드 호환성)
        init_db_sync()
        logger.info("✅ Database tables initialized (sync)")

        # 4. 비동기 DB 초기화 (새로운 holiday 테이블)
        await init_db_async()
        logger.info("✅ Database tables initialized (async)")

        # 5. 공휴일 배경 태스크 시작
        _asyncio_task = asyncio.create_task(holiday_task.run())
        logger.info("✅ Holiday background task scheduled")

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
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# Exception Handler 등록
register_exception_handlers(app)

# CORS 설정 (GraphQL 클라이언트를 위해)
# Bug Fix: allow_origins=["*"]와 allow_credentials=True는 호환되지 않음
# 개발 환경에서는 credentials를 False로 설정하거나 특정 origin을 지정해야 함
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 특정 도메인으로 제한
    allow_credentials=False,  # Bug Fix: "*" origin과 함께 사용 불가
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware 등록
app.add_middleware(RequestLoggerMiddleware)

# API Router 등록 (REST + GraphQL 모두 포함)
app.include_router(api_router)
