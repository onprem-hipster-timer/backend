"""
TodoGroup Domain Exceptions
"""
from fastapi import status

from app.core.error_handlers import DomainException


class TodoGroupNotFoundError(DomainException):
    """할 일 그룹을 찾을 수 없음"""
    status_code = status.HTTP_404_NOT_FOUND
    detail = "할 일 그룹을 찾을 수 없습니다"


class DefaultTodoGroupDeletionError(DomainException):
    """기본 할 일 그룹 삭제 시도"""
    status_code = status.HTTP_409_CONFLICT
    detail = "기본 할 일 그룹은 삭제할 수 없습니다"
