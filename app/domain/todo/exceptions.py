"""
Todo Domain Exceptions

아키텍처 원칙:
- Domain Exception은 status_code를 포함
- Exception Handler에서 HTTP로 자동 변환
"""
from app.core.error_handlers import DomainException


class TodoNotFoundError(DomainException):
    """Todo를 찾을 수 없음"""
    status_code = 404
    detail = "Todo not found"
