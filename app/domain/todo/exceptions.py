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


class NotATodoError(DomainException):
    """일정이 Todo가 아닌 경우"""
    status_code = 400
    detail = "This schedule is not a Todo"


class DeadlineRequiredForConversionError(DomainException):
    """Todo를 일정으로 변환할 때 마감 시간이 필요합니다"""
    status_code = 400
    detail = "Todo를 일정으로 변환하려면 마감 시간(start_time, end_time)이 필요합니다"
