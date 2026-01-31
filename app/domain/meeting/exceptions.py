"""
Meeting Domain Exceptions

일정 조율 관련 예외
"""
from fastapi import status

from app.core.error_handlers import DomainException


class MeetingNotFoundError(DomainException):
    """일정 조율을 찾을 수 없음"""
    status_code = status.HTTP_404_NOT_FOUND
    detail = "Meeting not found"


class MeetingParticipantNotFoundError(DomainException):
    """참여자를 찾을 수 없음"""
    status_code = status.HTTP_404_NOT_FOUND
    detail = "Meeting participant not found"


class InvalidDateRangeError(DomainException):
    """잘못된 날짜 범위"""
    status_code = status.HTTP_400_BAD_REQUEST
    detail = "Invalid date range: start_date must be <= end_date"


class InvalidTimeRangeError(DomainException):
    """잘못된 시간 범위"""
    status_code = status.HTTP_400_BAD_REQUEST
    detail = "Invalid time range: start_time must be < end_time"


class InvalidAvailableDaysError(DomainException):
    """잘못된 요일 설정"""
    status_code = status.HTTP_400_BAD_REQUEST
    detail = "Invalid available_days: must be list of integers 0-6"


class InvalidTimeSlotMinutesError(DomainException):
    """잘못된 시간 슬롯 단위"""
    status_code = status.HTTP_400_BAD_REQUEST
    detail = "Invalid time_slot_minutes: must be > 0"
