"""
Kratos admin API 클라이언트

탈퇴 신청 때 세션 폐기, 파기 때 identity 삭제, 미인증 가입 정리 때 identity 목록 조회에 쓴다. JWT sub가 Kratos identity id다.
게스트(app/domain/guest)는 identity 생성·조회·삭제에 쓴다.
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


async def list_identities() -> list[dict] | None:
    """모든 identity를 페이지를 따라가며 읽는다. 실패하면 None."""
    if not app_config.settings.KRATOS_ADMIN_URL:
        return None
    identities: list[dict] = []
    url: str | None = "/admin/identities?page_size=250"
    try:
        async with _make_client() as client:
            while url:
                response = await client.get(url)
                if response.status_code != 200:
                    logger.warning("Kratos identity 목록 조회 실패: status=%s", response.status_code)
                    return None
                identities.extend(response.json())
                url = response.links.get("next", {}).get("url")
    except httpx.HTTPError:
        logger.warning("Kratos identity 목록 조회 요청 실패", exc_info=True)
        return None
    return identities


# GET /admin/identities?ids=... 한 번에 묻는 id 수
IDENTITY_BATCH_SIZE = 100


async def create_identity(
        schema_id: str,
        traits: dict,
        password: str,
        verified_addresses: tuple[str, ...] = (),
) -> dict | None:
    """비밀번호 자격 증명을 가진 identity를 만든다. 만든 identity, 실패하면 None.

    admin API로 만들면 Kratos 비밀번호 정책이 적용되지 않는다. verified_addresses는 인증을 마친
    이메일 주소로 넣는다(schema에서 verification via email인 trait의 값이어야 한다).
    """
    if not app_config.settings.KRATOS_ADMIN_URL:
        return None
    body = {
        "schema_id": schema_id,
        "traits": traits,
        "state": "active",
        "credentials": {"password": {"config": {"password": password}}},
    }
    if verified_addresses:
        body["verifiable_addresses"] = [
            {"value": address, "via": "email", "verified": True, "status": "completed"}
            for address in verified_addresses
        ]
    try:
        async with _make_client() as client:
            response = await client.post("/admin/identities", json=body)
    except httpx.HTTPError:
        logger.warning("Kratos identity 생성 요청 실패", exc_info=True)
        return None
    if response.status_code != 201:
        logger.warning("Kratos identity 생성 실패: status=%s", response.status_code)
        return None
    return response.json()


async def get_identity(identity_id: str) -> dict | None:
    """identity 하나. 없거나 실패하면 None."""
    if not app_config.settings.KRATOS_ADMIN_URL:
        return None
    try:
        async with _make_client() as client:
            response = await client.get(_identity_path(identity_id))
    except httpx.HTTPError:
        logger.warning("Kratos identity 조회 요청 실패", exc_info=True)
        return None
    if response.status_code != 200:
        if response.status_code != 404:
            logger.warning("Kratos identity 조회 실패: status=%s", response.status_code)
        return None
    return response.json()


async def get_identities(identity_ids: list[str]) -> list[dict] | None:
    """주어진 id의 identity들 (없는 id는 빠진다). 실패하면 None."""
    if not app_config.settings.KRATOS_ADMIN_URL:
        return None
    wanted = set(identity_ids)
    found: list[dict] = []
    ids = list(dict.fromkeys(identity_ids))
    try:
        async with _make_client() as client:
            for start in range(0, len(ids), IDENTITY_BATCH_SIZE):
                batch = ids[start:start + IDENTITY_BATCH_SIZE]
                params = [("ids", identity_id) for identity_id in batch] + [("page_size", str(len(batch)))]
                response = await client.get("/admin/identities", params=params)
                if response.status_code != 200:
                    logger.warning("Kratos identity 조회 실패: status=%s", response.status_code)
                    return None
                found.extend(i for i in response.json() if i.get("id") in wanted)
    except httpx.HTTPError:
        logger.warning("Kratos identity 조회 요청 실패", exc_info=True)
        return None
    return found
