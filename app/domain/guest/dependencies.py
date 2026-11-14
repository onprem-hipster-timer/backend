"""
게스트를 받는 경로의 의존성

회원 의존성(get_current_user 등)은 게스트 토큰을 403으로 거부한다. 게스트를 받는 경로는 여기 의존성을 명시해서 쓴다.

- get_current_guest: 게스트 토큰만 통과 (GUEST_ENABLED가 꺼져 있으면 403)
- require_guest_access(resource_type, id_param): 경로 파라미터 id_param의 리소스에 접근할 수 있는 게스트 행.
  요청마다 게스트 행과 접근 정책(app/domain/guest/service.py check_access)을 확인하므로, 폐기된 게스트는
  JWT가 아직 유효해도 거부된다

테스트: tests/domain/guest/test_dependencies.py
"""
from typing import Awaitable, Callable
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials

import app.core.config as app_config
from app.core.auth import CurrentUser, authenticate_request, security
from app.domain.guest import service
from app.domain.guest.exceptions import GuestAccessDeniedError
from app.domain.guest.model import Guest
from app.models.visibility import ResourceType


async def get_current_guest(
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> CurrentUser:
    """FastAPI Dependency: 게스트 토큰의 사용자 (sub는 게스트의 Kratos identity id)"""
    if not app_config.settings.GUEST_ENABLED:
        raise GuestAccessDeniedError()
    user = await authenticate_request(request, credentials)
    if not user.is_guest:
        raise GuestAccessDeniedError()
    return user


def require_guest_access(
        resource_type: ResourceType,
        id_param: str,
) -> Callable[..., Awaitable[Guest]]:
    """경로 파라미터 id_param이 가리키는 resource_type 리소스의 게스트만 통과시키는 의존성을 만든다

    예: `guest: Guest = Depends(require_guest_access(ResourceType.MEETING, "meeting_id"))`
    """

    async def dependency(request: Request, user: CurrentUser = Depends(get_current_guest)) -> Guest:
        try:
            resource_id = UUID(str(request.path_params[id_param]))
        except (KeyError, ValueError):
            raise GuestAccessDeniedError()
        return await service.authorize(user.sub, resource_type, resource_id)

    return dependency
