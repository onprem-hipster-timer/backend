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


class TodoInvalidParentError(DomainException):
    """유효하지 않은 부모 Todo 참조"""
    status_code = 400
    detail = "Invalid parent Todo: parent does not exist"


class TodoSelfReferenceError(DomainException):
    """자기 자신을 부모로 설정 시도"""
    status_code = 400
    detail = "Cannot set Todo as its own parent"


class TodoCycleError(DomainException):
    """순환 참조 생성 시도"""
    status_code = 400
    detail = "Cannot create cycle in Todo hierarchy"


class TodoParentGroupMismatchError(DomainException):
    """부모와 자식의 tag_group_id 불일치"""
    status_code = 400
    detail = "Parent and child Todo must belong to the same tag group"


class TodoStatusLinkageMismatchError(DomainException):
    """UNSCHEDULED/SCHEDULED는 연동 유무 플래그 — 실제 연동 상태와 불일치하는 명시 값 거부"""
    status_code = 422
    detail = (
        "Status flag conflicts with linked schedule state: "
        "UNSCHEDULED/SCHEDULED must match whether a linked schedule exists"
    )


class LinkedSchedulePolicyRequiredError(DomainException):
    """연결 투영이 존재하는데 처리 정책이 누락됨"""
    status_code = 422
    detail = (
        "linked_schedule_policy is required because linked schedules exist. "
        "Choose 'delete' or 'unlink'."
    )
