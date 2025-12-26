import logging
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class RequestLoggerMiddleware(BaseHTTPMiddleware):
    """요청 로깅 미들웨어"""

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        # 요청 정보 로깅
        logger.info(
            f"Request: {request.method} {request.url.path}",
            extra={
                "method": request.method,
                "path": request.url.path,
                "client": request.client.host if request.client else None,
            }
        )

        response = await call_next(request)

        # 응답 시간 계산
        process_time = time.time() - start_time

        # 응답 정보 로깅
        logger.info(
            f"Response: {request.method} {request.url.path} - {response.status_code}",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "process_time": process_time,
            }
        )

        return response
