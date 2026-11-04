"""
Origin 검증 미들웨어

프록시(Cloudflare Worker 등)가 모든 요청에 붙이는 ORIGIN_VERIFY_HEADER 값을
ORIGIN_VERIFY_SECRET과 상수 시간으로 비교해, 프록시를 건너뛴 요청을 403으로 거부한다.
HTTP와 WebSocket 모두 검사한다.

- ORIGIN_VERIFY_HEADER/SECRET 둘 중 하나라도 비어 있으면 검사하지 않는다(로컬/테스트).
- 헬스 체크 경로는 검사하지 않는다. 컨테이너 startup probe가 프록시 없이 직접 호출한다.
"""
import hmac
import logging

from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core import config as app_config

logger = logging.getLogger(__name__)

# 프록시를 거치지 않고 호출되는 경로 (Cloud Run startup probe: GET /health)
EXEMPT_PATHS = frozenset({"/health"})


def origin_verify_enabled() -> bool:
    """ORIGIN_VERIFY_HEADER와 ORIGIN_VERIFY_SECRET이 모두 설정됐을 때만 검사"""
    return bool(app_config.settings.ORIGIN_VERIFY_HEADER and app_config.settings.ORIGIN_VERIFY_SECRET)


def is_valid_origin_header(value: str | None) -> bool:
    """헤더 값이 ORIGIN_VERIFY_SECRET과 같은지 상수 시간으로 비교"""
    if value is None:
        return False
    return hmac.compare_digest(
        value.encode("utf-8"),
        app_config.settings.ORIGIN_VERIFY_SECRET.encode("utf-8"),
    )


class OriginVerifyMiddleware:
    """전 요청(HTTP, WebSocket) Origin 검증 헤더 검사 (순수 ASGI)"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] not in ("http", "websocket")
            or not origin_verify_enabled()
            or scope["path"] in EXEMPT_PATHS
        ):
            await self.app(scope, receive, send)
            return

        header_name = app_config.settings.ORIGIN_VERIFY_HEADER.lower().encode("latin-1")
        value = None
        for name, raw in scope.get("headers", []):
            if name == header_name:
                value = raw.decode("latin-1")
                break

        if is_valid_origin_header(value):
            await self.app(scope, receive, send)
            return

        logger.warning(f"Origin verification failed: {scope['type']} {scope['path']}")
        if scope["type"] == "websocket":
            # accept 전에 close하면 서버가 HTTP 403으로 핸드셰이크를 거부한다
            await send({"type": "websocket.close", "code": 1008})
            return
        response = PlainTextResponse("Forbidden", status_code=403)
        await response(scope, receive, send)
