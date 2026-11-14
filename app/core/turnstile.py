"""
Cloudflare Turnstile 서버 확인 (siteverify)

게스트 생성(app/domain/guest)에서 클라이언트가 위젯에서 받은 토큰을 TURNSTILE_SECRET_KEY로 확인한다.
클라이언트 IP는 보내지 않는다. 토큰은 한 번만 확인할 수 있다.
"""
import httpx

import app.core.config as app_config


class TurnstileUnavailableError(Exception):
    """확인 엔드포인트에 닿지 않거나 200이 아니거나 응답을 읽을 수 없음"""


def _make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=3.0))


async def verify(token: str) -> bool:
    """토큰이 통과하면 True, 통과하지 못하면 False. 확인할 수 없으면 TurnstileUnavailableError"""
    settings = app_config.settings
    try:
        async with _make_client() as client:
            response = await client.post(
                settings.TURNSTILE_VERIFY_URL,
                data={"secret": settings.TURNSTILE_SECRET_KEY, "response": token},
            )
    except httpx.HTTPError as exc:
        raise TurnstileUnavailableError("siteverify request failed") from exc
    if response.status_code != 200:
        raise TurnstileUnavailableError(f"siteverify status={response.status_code}")
    try:
        success = response.json()["success"]
    except (ValueError, KeyError, TypeError) as exc:
        raise TurnstileUnavailableError("siteverify response unreadable") from exc
    if not isinstance(success, bool):
        raise TurnstileUnavailableError("siteverify response unreadable")
    return success
