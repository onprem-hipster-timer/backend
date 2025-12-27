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


class InvalidRecurrenceRuleError(DomainException):
    """잘못된 반복 규칙"""
    status_code = 400
    detail = "Invalid recurrence rule: RRULE format is invalid"


class InvalidRecurrenceEndError(DomainException):
    """잘못된 반복 종료일"""
    status_code = 400
    detail = "Invalid recurrence end: recurrence_end must be after start_time"


class NotRecurringScheduleError(DomainException):
    """반복 일정이 아닌 일정에 대한 작업"""
    status_code = 400
    detail = "This schedule is not a recurring schedule"