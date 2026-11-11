"""
내부 작업 엔드포인트 (/internal/*)

스케줄러가 호출한다. 사용자 인증이 아니라 공유 토큰으로 인증하고 공개 OpenAPI 스키마에 넣지 않는다.

- POST /internal/accounts/purge: 유예 기간이 지난 탈퇴 계정 파기 (app/domain/user/purge.py).
  X-Purge-Token이 ACCOUNT_PURGE_TOKEN과 같아야 하고, 설정이 비어 있으면 404
"""
import hmac

from fastapi import APIRouter, Header, HTTPException, status

import app.core.config as app_config
from app.domain.user.purge import purge_due_accounts

router = APIRouter(prefix="/internal", include_in_schema=False)


@router.post("/accounts/purge")
async def purge_accounts(x_purge_token: str | None = Header(default=None)) -> dict[str, int]:
    expected = app_config.settings.ACCOUNT_PURGE_TOKEN
    if not expected:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if not hmac.compare_digest((x_purge_token or "").encode(), expected.encode()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return await purge_due_accounts()
