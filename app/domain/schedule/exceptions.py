"""
Schedule Domain Exceptions

아키텍처 원칙:
- Domain Exception은 status_code를 포함
- Exception Handler에서 HTTP로 자동 변환
"""
from app.core.error_handlers import DomainException


class ScheduleNotFoundError(DomainException):
    """일정을 찾을 수 없음"""
    status_code = 404
    detail = "Schedule not found"


class InvalidScheduleTimeError(DomainException):
    """잘못된 일정 시간"""
    status_code = 400
    detail = "Invalid schedule time: end_time must be after start_time"
