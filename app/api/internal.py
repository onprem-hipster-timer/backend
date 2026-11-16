"""
내부 작업 엔드포인트 (/internal/*)

스케줄러가 호출한다. 사용자 인증이 아니라 공유 토큰으로 인증하고 공개 OpenAPI 스키마에 넣지 않는다.

- POST /internal/accounts/purge: 하루 한 번 실행. 유예 기간이 지난 탈퇴 계정 파기 (app/domain/user/purge.py)와
  EXPIRED·MISSING 리소스의 게스트 폐기 (app/domain/guest/service.py의 discard_stale_guests).
  응답은 purge_due_accounts의 키(purged, kratos_pending, unverified_removed)와 폐기한 게스트 수 guests_discarded.
  X-Purge-Token이 ACCOUNT_PURGE_TOKEN과 같아야 하고, 설정이 비어 있으면 404

테스트: tests/test_account_purge_e2e.py, tests/test_unverified_signup_cleanup.py, tests/domain/guest/test_stale_guests.py
"""
import hmac

from fastapi import APIRouter, Header, HTTPException, status

import app.core.config as app_config
from app.domain.guest.service import discard_stale_guests
from app.domain.user.purge import purge_due_accounts

router = APIRouter(prefix="/internal", include_in_schema=False)


@router.post("/accounts/purge")
async def purge_accounts(x_purge_token: str | None = Header(default=None)) -> dict[str, int]:
    expected = app_config.settings.ACCOUNT_PURGE_TOKEN
    if not expected:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if not hmac.compare_digest((x_purge_token or "").encode(), expected.encode()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    result = await purge_due_accounts()
    result["guests_discarded"] = await discard_stale_guests()
    return result
