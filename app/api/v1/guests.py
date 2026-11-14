"""
Guests Router

리소스 하나에 속한 게스트 계정 (docs/guides/guest.ko.md). GUEST_ENABLED가 꺼져 있으면 모두 404.

- POST /v1/guests/enter: 인증 없음. 이름·비밀번호가 맞는 게스트로 다시 들어가거나 새 게스트를 만들고
  Kratos 세션 토큰을 돌려준다. JWT는 회원처럼 /auth/sessions/whoami?tokenize_as=api로 받는다
- DELETE /v1/guests/me: 게스트 토큰. 게스트가 자기를 폐기한다

테스트: tests/domain/guest/test_guest_api.py
"""
from fastapi import APIRouter, Depends, HTTPException, Response, status

import app.core.config as app_config
from app.core.auth import CurrentUser
from app.core.config import settings
from app.domain.guest import service
from app.domain.guest.dependencies import get_current_guest
from app.domain.guest.schema.dto import GuestEnter, GuestEnterRead


def require_guest_enabled() -> None:
    if not app_config.settings.GUEST_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)


router = APIRouter(
    prefix="/guests",
    tags=["Guests"],
    dependencies=[Depends(require_guest_enabled)],
    include_in_schema=settings.GUEST_ENABLED,
)


@router.post("/enter", response_model=GuestEnterRead)
async def enter_as_guest(data: GuestEnter):
    """
    리소스에 게스트로 들어간다.

    이 리소스에서 이름이 같고 비밀번호가 맞는 게스트가 있으면 그 게스트로, 없으면 새 게스트로 들어간다.
    이름은 겹칠 수 있고, 같은 이름은 리소스당 10명까지다(넘으면 409).
    리소스가 없거나 지금 게스트를 받지 않으면 403.
    """
    return await service.enter(data)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(guest: CurrentUser = Depends(get_current_guest)) -> Response:
    """게스트가 자기를 폐기한다. Kratos 세션은 바로 끊기고, 이미 받은 JWT도 게스트 경로에서 거부된다."""
    await service.discard_guest(guest.sub)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
