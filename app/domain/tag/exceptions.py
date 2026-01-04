"""
Tag Domain Exceptions
"""
from fastapi import status

from app.core.error_handlers import DomainException


class TagGroupNotFoundError(DomainException):
    """태그 그룹을 찾을 수 없음"""
    status_code = status.HTTP_404_NOT_FOUND
    detail = "태그 그룹을 찾을 수 없습니다"


class TagNotFoundError(DomainException):
    """태그를 찾을 수 없음"""
    status_code = status.HTTP_404_NOT_FOUND
    detail = "태그를 찾을 수 없습니다"


class DuplicateTagNameError(DomainException):
    """그룹 내 태그 이름 중복"""
    status_code = status.HTTP_409_CONFLICT
    detail = "그룹 내 태그 이름이 중복됩니다"
