from contextlib import asynccontextmanager
from fastapi import FastAPI

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

# Middleware 등록
app.add_middleware(RequestLoggerMiddleware)

# API Router 등록
app.include_router(api_router)
