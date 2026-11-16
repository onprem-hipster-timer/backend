"""
Guests Router

리소스 하나에 속한 게스트 계정 (docs/guides/guest.ko.md). GUEST_ENABLED가 꺼져 있으면 모두 404.

- POST /v1/guests/lookup: 인증 없음. 리소스에서 그 이름의 게스트 로그인 식별자(handle)와 현재 약관 버전을 돌려준다
- POST /v1/guests: 인증 없음. 약관 동의(consent)를 받아 새 게스트를 만들고 handle을 돌려준다
  클라이언트는 handle과 비밀번호로 회원처럼 /auth로 Kratos에 로그인하고 JWT를 받는다
- DELETE /v1/guests/me: 게스트 토큰. 게스트가 자기를 폐기한다
- PUT /v1/guests/me/consent: 게스트 토큰. 현재 약관 버전 동의를 기록한다

이름 찾기·생성·자기 삭제는 Cloudflare Turnstile 토큰을 X-Turnstile-Token 헤더로 받고, 라우트에 닿기 전에 인터셉터가 확인한다
(app/middleware/guest_gate.py). 동의 기록은 Turnstile 토큰을 받지 않는다.
CONSENT_ENFORCED면 현재 약관 버전에 동의하지 않은 게스트는 동의 기록과 자기 삭제 밖의 게스트 경로가 428이다
(app/domain/guest/dependencies.py).

테스트: tests/domain/guest/test_guest_api.py, tests/domain/guest/test_consent.py
"""
from fastapi import APIRouter, Depends, HTTPException, Response, status

import app.core.config as app_config
from app.core.auth import CurrentUser
from app.core.config import settings
from app.domain.consent.schema.dto import ConsentCreate
from app.domain.guest import service
from app.domain.guest.dependencies import get_current_guest
from app.domain.guest.schema.dto import GuestCreate, GuestLookup, GuestLookupRead, GuestRead


def require_guest_enabled() -> None:
    if not app_config.settings.GUEST_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)


router = APIRouter(
    prefix="/guests",
    tags=["Guests"],
    dependencies=[Depends(require_guest_enabled)],
    include_in_schema=settings.GUEST_ENABLED,
)


@router.post("/lookup", response_model=GuestLookupRead)
async def lookup_guest(data: GuestLookup):
    """
    리소스에서 이름이 같은 게스트의 로그인 식별자(handle)를 찾는다. 없으면 handle은 null.
    `consent_version`은 현재 약관 시행일이다. 게스트를 만들 때 `consent.version`으로 보낸다.

    리소스가 없거나 지금 게스트를 받지 않으면 403.
    X-Turnstile-Token 헤더의 토큰이 확인을 통과하지 못하면 403, 확인할 수 없으면 503 (다른 확인보다 먼저다).
    """
    return await service.lookup(data)


@router.post("", response_model=GuestRead, status_code=status.HTTP_201_CREATED)
async def create_guest(data: GuestCreate):
    """
    리소스에 새 게스트를 만든다. 로그인은 응답의 handle과 비밀번호로 Kratos에 한다.

    `consent`는 만 14세 이상·이용약관·개인정보처리방침 동의로 세 항목 모두 true여야 한다(아니면 422).
    `consent.version`이 현재 약관 시행일이 아니면 409이고, 리소스·이름 확인보다 먼저다.
    이름은 리소스 안에서 겹치지 않는다(이미 있으면 409). 리소스의 게스트가 100명이면 409.
    리소스가 없거나 지금 게스트를 받지 않으면 403.
    X-Turnstile-Token 헤더의 토큰이 확인을 통과하지 못하면 403, 확인할 수 없으면 503 (다른 확인보다 먼저다).
    """
    return await service.create(data)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(guest: CurrentUser = Depends(get_current_guest)) -> Response:
    """게스트가 자기를 폐기한다. Kratos 세션은 바로 끊기고, 이미 받은 JWT도 게스트 경로에서 거부된다.

    X-Turnstile-Token 헤더의 토큰이 확인을 통과하지 못하면 403, 확인할 수 없으면 503.
    """
    await service.discard_guest(guest.sub)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/me/consent", status_code=status.HTTP_204_NO_CONTENT)
async def put_my_consent(data: ConsentCreate, guest: CurrentUser = Depends(get_current_guest)) -> Response:
    """
    게스트의 만 14세 이상 확인, 이용약관, 개인정보처리방침 동의 기록. 본문은 회원 동의와 같다.

    `version`은 POST /v1/guests/lookup이 돌려준 현재 약관 시행일이어야 한다(다르면 409).
    게스트가 폐기되었으면 403. Turnstile 토큰은 받지 않는다.
    """
    await service.record_consent(guest.sub, data)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
