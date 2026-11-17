"""
게스트를 받는 경로의 의존성

회원 의존성(get_current_user 등)은 게스트 토큰을 403으로 거부한다. 게스트를 받는 경로는 여기 의존성을 명시해서 쓴다.

- get_current_guest: 게스트 토큰만 통과 (GUEST_ENABLED가 꺼져 있으면 403, schema_id 클레임이 없으면 401).
  CONSENT_ENFORCED면 현재 약관 버전에 동의하지 않은 게스트는 GUEST_CONSENT_ALLOWED_ROUTES 밖이면 428
- require_guest_access(resource_type, id_param): 경로 파라미터 id_param의 리소스에 접근할 수 있는 게스트 행.
  요청마다 게스트 행과 접근 정책(app/domain/guest/service.py check_access)을 확인하므로, 폐기된 게스트는
  JWT가 아직 유효해도 거부된다
- guest_from_token(token): 요청 본문으로 받은 게스트 JWT의 사용자 (게스트 가져오기)

테스트: tests/domain/guest/test_dependencies.py, tests/domain/guest/test_consent.py,
tests/domain/guest/test_meeting_guest_import.py
"""
from typing import Awaitable, Callable
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials

import app.core.config as app_config
from app.core.auth import CurrentUser, authenticate_request, require_schema_id, security, verify_access_token
from app.domain.consent.exceptions import ConsentRequiredError
from app.domain.guest import service
from app.domain.guest.exceptions import GuestAccessDeniedError, GuestTokenInvalidError
from app.domain.guest.model import Guest
from app.models.visibility import ResourceType


# 현재 약관 버전에 동의하지 않은 게스트도 부를 수 있는 경로 (동의하지 않으면 자기를 폐기할 수 있어야 한다)
GUEST_CONSENT_ALLOWED_ROUTES = frozenset({
    ("PUT", "/v1/guests/me/consent"),
    ("DELETE", "/v1/guests/me"),
})


async def get_current_guest(
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> CurrentUser:
    """FastAPI Dependency: 게스트 토큰의 사용자 (sub는 게스트의 Kratos identity id)"""
    if not app_config.settings.GUEST_ENABLED:
        raise GuestAccessDeniedError()
    user = await authenticate_request(request, credentials)
    if app_config.settings.OIDC_ENABLED:
        require_schema_id(user)
    if not user.is_guest:
        raise GuestAccessDeniedError()
    if (
        app_config.settings.CONSENT_ENFORCED
        and (request.method, request.url.path) not in GUEST_CONSENT_ALLOWED_ROUTES
        and await service.consent_pending(user.sub)
    ):
        raise ConsentRequiredError()
    return user


async def guest_from_token(token: str) -> CurrentUser:
    """요청 본문으로 받은 게스트 JWT의 사용자 (게스트 가져오기). 검증은 Authorization 헤더의 토큰과 같다.

    검증에 실패하거나(서명·iss·aud·exp, sub) 게스트 토큰이 아니면 GuestTokenInvalidError(422).
    본문의 토큰이라 401을 쓰지 않는다(요청한 회원의 인증과 따로다). JWKS를 받지 못하면 503 그대로
    """
    try:
        user = await verify_access_token(token)
    except HTTPException as e:
        if e.status_code != status.HTTP_401_UNAUTHORIZED:
            raise
        raise GuestTokenInvalidError() from None
    if not user.is_guest:
        raise GuestTokenInvalidError()
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
