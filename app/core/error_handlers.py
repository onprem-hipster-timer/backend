import logging
from datetime import datetime
from uuid import uuid4

from fastapi import Request, status
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class ErrorResponse:
    """표준화된 에러 응답"""

    def __init__(
            self,
            error_id: str,
            status_code: int,
            error_type: str,
            message: str,
            timestamp: str,
            path: str,
    ):
        self.error_id = error_id
        self.status_code = status_code
        self.error_type = error_type
        self.message = message
        self.timestamp = timestamp
        self.path = path

    def dict(self):
        return {
            "error_id": self.error_id,
            "status_code": self.status_code,
            "error_type": self.error_type,
            "message": self.message,
            "timestamp": self.timestamp,
            "path": self.path,
        }


class DomainException(Exception):
    """모든 Domain 예외의 베이스"""
    status_code: int = 400
    detail: str = "Business logic error"

    def __init__(self, detail: str = None):
        if detail:
            self.detail = detail
        super().__init__(self.detail)


async def domain_exception_handler(
        request: Request, exc: DomainException
) -> JSONResponse:
    """Domain Exception → HTTP"""
    error_id = str(uuid4())

    error_response = ErrorResponse(
        error_id=error_id,
        status_code=exc.status_code,
        error_type=exc.__class__.__name__,
        message=exc.detail,
        timestamp=datetime.utcnow().isoformat(),
        path=str(request.url.path),
    )

    logger.warning(
        f"Domain exception occurred",
        extra={
            "error_id": error_id,
            "error_type": exc.__class__.__name__,
            "message": exc.detail,
            "path": request.url.path,
            "method": request.method,
            "status_code": exc.status_code,
        }
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.dict(),
    )


async def global_exception_handler(
        request: Request, exc: Exception
) -> JSONResponse:
    """예상 못한 Exception"""
    error_id = str(uuid4())

    error_response = ErrorResponse(
        error_id=error_id,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_type="InternalServerError",
        message="An unexpected error occurred. Please contact support with error_id.",
        timestamp=datetime.utcnow().isoformat(),
        path=str(request.url.path),
    )

    logger.error(
        f"Unexpected exception occurred",
        extra={
            "error_id": error_id,
            "path": request.url.path,
            "method": request.method,
            "exception_type": exc.__class__.__name__,
        },
        exc_info=True,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response.dict(),
    )


def register_exception_handlers(app):
    """main.py에서 호출하여 Exception Handler 등록"""
    app.add_exception_handler(DomainException, domain_exception_handler)
    app.add_exception_handler(Exception, global_exception_handler)
