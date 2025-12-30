"""
Timer Domain Exceptions

아키텍처 원칙:
- Domain Exception은 status_code를 포함
- Exception Handler에서 HTTP로 자동 변환
"""
from app.core.error_handlers import DomainException


class TimerNotFoundError(DomainException):
    """타이머를 찾을 수 없음"""
    status_code = 404
    detail = "Timer not found"


class InvalidTimerStatusError(DomainException):
    """잘못된 타이머 상태 전이"""
    status_code = 400
    detail = "Invalid timer status transition"


class TimerAlreadyRunningError(DomainException):
    """이미 실행 중인 타이머"""
    status_code = 400
    detail = "Timer is already running"


class TimerNotRunningError(DomainException):
    """실행 중이 아닌 타이머"""
    status_code = 400
    detail = "Timer is not running"
