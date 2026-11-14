"""
Kratos 훅 수신 엔드포인트 (/internal/kratos/hooks/*)

게스트를 켠 Kratos 설정의 web_hook이 호출한다 (docs/deployment/kratos-guest.ko.md). 공개 OpenAPI 스키마에 넣지 않는다.

- GUEST_ENABLED가 꺼져 있으면 404
- X-Kratos-Hook-Key 헤더가 KRATOS_HOOK_API_KEY와 같아야 한다. 다르거나 없으면 401
- 허용은 200 `{}`, 거절은 403과 Kratos 메시지 형식(`messages`). Kratos는 거절을 플로우 메시지로 돌려준다

POST /internal/kratos/hooks/login: 로그인(password) 직후. 회원은 인증된 주소가 있어야 하고,
  게스트는 게스트 행이 있고 접근 정책이 허용해야 한다 (app/domain/guest/service.py login_allowed)
POST /internal/kratos/hooks/settings/{method}: 설정 저장 직전 (profile, password, oidc).
  게스트는 로그인 식별자(handle)를 그대로 둔 이름 변경만 된다 (settings_change_allowed)

테스트: tests/domain/guest/test_kratos_hooks.py
"""
import hmac
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import app.core.config as app_config
from app.domain.guest import service

HOOK_KEY_HEADER = "X-Kratos-Hook-Key"

# Kratos text id. 4000010은 Kratos가 이메일을 인증하지 않은 로그인에 쓰는 id와 같다
UNVERIFIED_ADDRESS_MESSAGE_ID = 4000010
REFUSED_MESSAGE_ID = 4000001

router = APIRouter(prefix="/internal/kratos/hooks", include_in_schema=False)


class LoginHookBody(BaseModel):
    identity_id: str
    schema_id: str | None = None
    verified: bool = False


class SettingsHookBody(BaseModel):
    identity_id: str
    schema_id: str | None = None
    traits: dict[str, Any] = {}


def _authorize(key: str | None) -> None:
    if not app_config.settings.GUEST_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    expected = app_config.settings.KRATOS_HOOK_API_KEY
    if not expected or not hmac.compare_digest((key or "").encode(), expected.encode()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)


def _allowed() -> JSONResponse:
    return JSONResponse({}, status_code=status.HTTP_200_OK)


def _refused(message_id: int, text: str) -> JSONResponse:
    return JSONResponse(
        {
            "messages": [
                {
                    "instance_ptr": "#/",
                    "messages": [{"id": message_id, "text": text, "type": "error", "context": {}}],
                }
            ]
        },
        status_code=status.HTTP_403_FORBIDDEN,
    )


@router.post("/login")
async def login_hook(
        body: LoginHookBody,
        x_kratos_hook_key: str | None = Header(default=None),
) -> JSONResponse:
    _authorize(x_kratos_hook_key)
    if await service.login_allowed(body.identity_id, body.schema_id, body.verified):
        return _allowed()
    if service.is_guest_schema(body.schema_id):
        return _refused(REFUSED_MESSAGE_ID, "This guest account cannot sign in.")
    return _refused(UNVERIFIED_ADDRESS_MESSAGE_ID, "Account not active yet. Did you forget to verify your email address?")


@router.post("/settings/{method}")
async def settings_hook(
        method: Literal["profile", "password", "oidc"],
        body: SettingsHookBody,
        x_kratos_hook_key: str | None = Header(default=None),
) -> JSONResponse:
    _authorize(x_kratos_hook_key)
    if await service.settings_change_allowed(method, body.identity_id, body.schema_id, body.traits):
        return _allowed()
    return _refused(REFUSED_MESSAGE_ID, "Guest accounts can only change their name.")
