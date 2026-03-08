"""
Visibility Router

리소스 접근권한 설정 REST API 엔드포인트
모든 도메인(todo, schedule, timer, meeting)의 접근권한을 중앙에서 관리합니다.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from app.core.auth import CurrentUser, get_current_user
from app.crud import meeting as meeting_crud
from app.crud import schedule as schedule_crud
from app.crud import timer as timer_crud
from app.crud import todo as todo_crud
from app.db.session import get_db_transactional
from app.domain.visibility.enums import ResourceType
from app.domain.visibility.exceptions import AccessDeniedError
from app.domain.visibility.schema.dto import VisibilityUpdate, VisibilityRead
from app.domain.visibility.service import VisibilityService

router = APIRouter(prefix="/visibility", tags=["Visibility"])

_RESOURCE_LOADERS = {
    ResourceType.TODO: todo_crud.get_todo_by_id,
    ResourceType.SCHEDULE: schedule_crud.get_schedule_by_id,
    ResourceType.TIMER: timer_crud.get_timer_by_id,
    ResourceType.MEETING: meeting_crud.get_meeting_by_id,
}


def _require_resource_owner(
        session: Session,
        resource_type: ResourceType,
        resource_id: UUID,
        current_user: CurrentUser,
) -> None:
    """리소스 소유권 검증. 소유자가 아니면 AccessDeniedError 발생."""
    loader = _RESOURCE_LOADERS[resource_type]
    resource = loader(session, resource_id)
    if not resource:
        from app.domain.visibility.exceptions import VisibilityNotFoundError
        raise VisibilityNotFoundError()
    if resource.owner_id != current_user.sub:
        raise AccessDeniedError()


@router.put(
    "/{resource_type}/{resource_id}",
    response_model=VisibilityRead,
    status_code=status.HTTP_200_OK,
)
async def set_visibility(
        resource_type: ResourceType,
        resource_id: UUID,
        data: VisibilityUpdate,
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    리소스 접근권한 설정/업데이트

    소유자만 접근권한을 설정할 수 있습니다.
    """
    _require_resource_owner(session, resource_type, resource_id, current_user)

    service = VisibilityService(session, current_user)
    service.set_visibility(
        resource_type=resource_type,
        resource_id=resource_id,
        level=data.level,
        allowed_user_ids=data.allowed_user_ids,
        allowed_emails=data.allowed_emails,
        allowed_domains=data.allowed_domains,
    )

    return service.get_visibility(resource_type, resource_id)


@router.get(
    "/{resource_type}/{resource_id}",
    response_model=VisibilityRead,
)
async def get_visibility(
        resource_type: ResourceType,
        resource_id: UUID,
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    리소스 접근권한 설정 조회

    소유자만 접근권한 설정을 조회할 수 있습니다.
    """
    _require_resource_owner(session, resource_type, resource_id, current_user)

    service = VisibilityService(session, current_user)
    visibility = service.get_visibility(resource_type, resource_id)
    if not visibility:
        from app.domain.visibility.exceptions import VisibilityNotFoundError
        raise VisibilityNotFoundError()

    return visibility


@router.delete(
    "/{resource_type}/{resource_id}",
    status_code=status.HTTP_200_OK,
)
async def delete_visibility(
        resource_type: ResourceType,
        resource_id: UUID,
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    리소스 접근권한 설정 삭제 (PRIVATE으로 복귀)

    소유자만 접근권한을 삭제할 수 있습니다.
    """
    _require_resource_owner(session, resource_type, resource_id, current_user)

    service = VisibilityService(session, current_user)
    service.delete_visibility(resource_type, resource_id)
    return {"ok": True}
