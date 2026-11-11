"""
Kratos admin API 클라이언트

탈퇴 신청 때 세션 폐기, 파기 때 identity 삭제에 쓴다. JWT sub가 Kratos identity id다.
KRATOS_ADMIN_URL이 비어 있으면 호출하지 않는다.
"""
import logging
from urllib.parse import quote

import httpx

import app.core.config as app_config

logger = logging.getLogger(__name__)


def _make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=app_config.settings.KRATOS_ADMIN_URL,
        timeout=httpx.Timeout(15.0, connect=3.0),
    )


def _identity_path(identity_id: str) -> str:
    return f"/admin/identities/{quote(identity_id, safe='')}"


async def revoke_sessions(identity_id: str) -> bool:
    """identity의 모든 세션 폐기. 성공(identity가 없는 404 포함)하면 True, 실패는 로그만 남기고 False."""
    if not app_config.settings.KRATOS_ADMIN_URL:
        logger.warning("KRATOS_ADMIN_URL이 비어 있어 세션을 폐기하지 않음")
        return False
    try:
        async with _make_client() as client:
            response = await client.delete(f"{_identity_path(identity_id)}/sessions")
    except httpx.HTTPError:
        logger.warning("Kratos 세션 폐기 요청 실패", exc_info=True)
        return False
    if response.status_code in (204, 404):
        return True
    logger.warning("Kratos 세션 폐기 실패: status=%s", response.status_code)
    return False


async def delete_identity(identity_id: str) -> bool:
    """identity 삭제. 성공하거나 이미 없으면(404) True, 실패하면 False."""
    if not app_config.settings.KRATOS_ADMIN_URL:
        logger.warning("KRATOS_ADMIN_URL이 비어 있어 identity를 삭제하지 않음")
        return False
    try:
        async with _make_client() as client:
            response = await client.delete(_identity_path(identity_id))
    except httpx.HTTPError:
        logger.warning("Kratos identity 삭제 요청 실패", exc_info=True)
        return False
    if response.status_code in (204, 404):
        return True
    logger.warning("Kratos identity 삭제 실패: status=%s", response.status_code)
    return False
