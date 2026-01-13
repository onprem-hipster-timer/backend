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


class RecurringScheduleError(DomainException):
    """반복 일정 관련 에러 (반복 일정이 아닌 일정에 반복 일정 작업 시도)"""
    status_code = 400
    detail = "This schedule is not a recurring schedule"


class ScheduleAlreadyLinkedToTodoError(DomainException):
    """이미 Todo와 연결된 Schedule"""
    status_code = 400
    detail = "This schedule is already linked to a Todo. Cannot create another Todo from it."
