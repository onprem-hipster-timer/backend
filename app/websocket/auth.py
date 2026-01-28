"""
WebSocket 인증

JWT 토큰 기반 WebSocket 연결 인증
Sec-WebSocket-Protocol 헤더에서 토큰을 추출합니다.

보안:
- 쿼리 파라미터를 통한 토큰 전달은 지원하지 않습니다 (로그 노출 위험)
- 반드시 Sec-WebSocket-Protocol 헤더를 사용하세요
"""
import logging
from typing import Optional

from fastapi import WebSocket, WebSocketException, status

from app.core.auth import CurrentUser, oidc_client
from app.core.config import settings

logger = logging.getLogger(__name__)


async def authenticate_websocket(websocket: WebSocket) -> Optional[CurrentUser]:
    """
    WebSocket 연결 인증

    토큰 추출:
    - Sec-WebSocket-Protocol 헤더 (authorization.bearer.{token})

    보안상의 이유로 쿼리 파라미터를 통한 토큰 전달은 지원하지 않습니다.
    OIDC가 비활성화된 경우 테스트 사용자 반환
    """
    # OIDC 비활성화 시 테스트 사용자 사용
    if not settings.OIDC_ENABLED:
        logger.warning("OIDC disabled - using test user for WebSocket")
        return CurrentUser(
            sub="test-user-id",
            email="test@example.com",
            name="Test User",
        )

    # Sec-WebSocket-Protocol에서만 토큰 추출 (보안상 쿼리 파라미터 미지원)
    token = None
    protocols = websocket.headers.get("sec-websocket-protocol", "")
    for protocol in protocols.split(","):
        protocol = protocol.strip()
        if protocol.startswith("authorization.bearer."):
            token = protocol.replace("authorization.bearer.", "")
            break

    if not token:
        logger.warning("WebSocket authentication failed: No token in Sec-WebSocket-Protocol header")
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Authentication required. Use Sec-WebSocket-Protocol header with authorization.bearer.{token}"
        )

    # 토큰 검증
    try:
        claims = await oidc_client.verify_token(token)
        sub = claims.get("sub")
        if not sub:
            raise WebSocketException(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Token missing 'sub' claim"
            )

        return CurrentUser(
            sub=sub,
            email=claims.get("email"),
            name=claims.get("name"),
            raw_claims=claims,
        )
    except Exception as e:
        logger.error(f"WebSocket token verification failed: {e}")
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Token verification failed"
        )


def get_websocket_subprotocol(websocket: WebSocket) -> Optional[str]:
    """
    클라이언트가 요청한 서브프로토콜 중 지원하는 것 반환

    인증 토큰이 Sec-WebSocket-Protocol로 전달된 경우,
    해당 프로토콜을 응답에 포함해야 연결이 성립됩니다.
    """
    protocols = websocket.headers.get("sec-websocket-protocol", "")
    for protocol in protocols.split(","):
        protocol = protocol.strip()
        if protocol.startswith("authorization.bearer."):
            return protocol
    return None
