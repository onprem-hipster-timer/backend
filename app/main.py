from contextlib import asynccontextmanager
from fastapi import FastAPI

from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import setup_logging
from app.core.error_handlers import register_exception_handlers
from app.db.session import init_db
from app.api.v1 import api_router
from app.middleware.request_logger import RequestLoggerMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 생명주기 관리"""
    # Startup
    setup_logging()
    init_db()
    yield
    # Shutdown (필요시 추가)


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
