"""
Kratos 공개 API 클라이언트 (backend가 직접 부르는 호출)

게스트 입장(app/domain/guest)에서 비밀번호 로그인(API 플로우)으로 세션 토큰을 받는다.
클라이언트 요청을 넘기는 /auth/* 프록시는 app/api/auth_proxy.py다.
"""
import logging

import httpx

import app.core.config as app_config

logger = logging.getLogger(__name__)


class KratosUnavailableError(Exception):
    """Kratos 공개 API에 닿지 않거나 예상하지 못한 응답"""


def _make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=app_config.settings.KRATOS_PUBLIC_URL,
        timeout=httpx.Timeout(15.0, connect=3.0),
        headers={"accept": "application/json"},
    )


async def password_login(identifier: str, password: str) -> str | None:
    """비밀번호 로그인. 성공하면 세션 토큰, 자격 증명이 맞지 않거나 로그인이 거절되면 None.

    Kratos에 닿지 않거나 5xx·예상하지 못한 응답이면 KratosUnavailableError.
    """
    try:
        async with _make_client() as client:
            flow = await client.get("/self-service/login/api")
            if flow.status_code != 200:
                raise KratosUnavailableError(f"login flow status={flow.status_code}")
            response = await client.post(
                "/self-service/login",
                params={"flow": flow.json()["id"]},
                json={"method": "password", "identifier": identifier, "password": password},
            )
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise KratosUnavailableError("login request failed") from exc
    if response.status_code == 200:
        try:
            token = response.json().get("session_token")
        except (ValueError, AttributeError):
            token = None
        if not token:
            raise KratosUnavailableError("login response without session_token")
        return token
    if response.status_code >= 500:
        raise KratosUnavailableError(f"login status={response.status_code}")
    return None
