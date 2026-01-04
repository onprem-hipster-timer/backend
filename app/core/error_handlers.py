import logging
from datetime import datetime, UTC
from typing import Dict, Any
from uuid import uuid4

from fastapi import Request, status
from fastapi.responses import JSONResponse
from strawberry.extensions import SchemaExtension

from app.core.config import settings

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


# ============================================================================
# 공통 에러 처리 함수
# ============================================================================

def format_error_response(
        exc: Exception,
        path: str,
        method: str = "POST",
) -> ErrorResponse:
    """
    단일 지점에서 에러 응답 포맷팅
    
    REST API와 GraphQL 모두에서 사용하는 공통 에러 처리 함수입니다.
    모든 에러 처리 로직이 여기서 관리됩니다.
    
    :param exc: 발생한 예외
    :param path: 요청 경로
    :param method: HTTP 메서드
    :return: ErrorResponse 객체
    """
    error_id = str(uuid4())
    timestamp = datetime.now(UTC).isoformat()

    # DomainException 처리
    if isinstance(exc, DomainException):
        logger.warning(
            f"Domain exception occurred",
            extra={
                "error_id": error_id,
                "error_type": exc.__class__.__name__,
                "error_message": exc.detail,
                "path": path,
                "method": method,
                "status_code": exc.status_code,
            }
        )

        return ErrorResponse(
            error_id=error_id,
            status_code=exc.status_code,
            error_type=exc.__class__.__name__,
            message=exc.detail,
            timestamp=timestamp,
            path=path,
        )

    # 내부 예외 처리
    logger.error(
        f"Unexpected exception occurred",
        extra={
            "error_id": error_id,
            "path": path,
            "method": method,
            "exception_type": exc.__class__.__name__,
        },
        exc_info=True,
    )

    # 프로덕션/개발 환경에 따른 메시지
    if settings.DEBUG:
        message = f"{exc.__class__.__name__}: {str(exc)}"
    else:
        message = "An unexpected error occurred. Please contact support with error_id."

    return ErrorResponse(
        error_id=error_id,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_type="InternalServerError",
        message=message,
        timestamp=timestamp,
        path=path,
    )


def format_error_for_graphql(
        exc: Exception,
        path: str = "/v1/graphql",
) -> Dict[str, Any]:
    """
    GraphQL용 에러 포맷팅
    
    format_error_response를 사용하여 GraphQL extensions 형식으로 변환합니다.
    
    :param exc: 발생한 예외
    :param path: 요청 경로
    :return: GraphQL extensions에 사용할 딕셔너리
    """
    error_response = format_error_response(exc, path, method="POST")
    return error_response.dict()


# ============================================================================
# FastAPI Exception Handlers
# ============================================================================

async def domain_exception_handler(
        request: Request, exc: DomainException
) -> JSONResponse:
    """Domain Exception → HTTP (format_error_response 사용)"""
    error_response = format_error_response(
        exc,
        path=str(request.url.path),
        method=request.method,
    )

    return JSONResponse(
        status_code=error_response.status_code,
        content=error_response.dict(),
    )


async def global_exception_handler(
        request: Request, exc: Exception
) -> JSONResponse:
    """예상 못한 Exception (format_error_response 사용)"""
    error_response = format_error_response(
        exc,
        path=str(request.url.path),
        method=request.method,
    )

    return JSONResponse(
        status_code=error_response.status_code,
        content=error_response.dict(),
    )


def register_exception_handlers(app):
    """main.py에서 호출하여 Exception Handler 등록"""
    app.add_exception_handler(DomainException, domain_exception_handler)
    app.add_exception_handler(Exception, global_exception_handler)


# ============================================================================
# GraphQL Extension
# ============================================================================

class GraphQLErrorHandlingExtension(SchemaExtension):
    """
    GraphQL 에러 처리 Extension
    
    error_handlers.py의 format_error_for_graphql을 사용하여
    모든 에러 처리를 단일 지점에서 관리합니다.
    """

    def on_operation(self):
        """요청 종료 시 에러 포맷팅 (on_operation 사용)"""
        yield  # operation 실행
        
        # operation 후 에러 포맷팅
        result = self.execution_context.result

        if result and result.errors:
            # GraphQL 경로 추출
            path = "/v1/graphql"
            if hasattr(self.execution_context, 'request'):
                try:
                    path = str(self.execution_context.request.url.path)
                except:
                    pass

            formatted_errors = []
            for error in result.errors:
                original_error = error.original_error if hasattr(error,
                                                                 'original_error') and error.original_error else None

                if original_error:
                    # 기존 error_handlers.py의 함수 사용
                    extensions = format_error_for_graphql(original_error, path)

                    # 에러 메시지와 extensions 업데이트
                    error.message = extensions["message"]
                    if not hasattr(error, 'extensions') or error.extensions is None:
                        error.extensions = {}
                    error.extensions.update(extensions)

                formatted_errors.append(error)

            result.errors = formatted_errors
