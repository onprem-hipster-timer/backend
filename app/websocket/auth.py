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

from fastapi import Depends, WebSocket, WebSocketException, status

from app.core.auth import CurrentUser, ensure_member, oidc_client
from app.core.config import settings

logger = logging.getLogger(__name__)


async def authenticate_websocket(websocket: WebSocket) -> CurrentUser:
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
        return CurrentUser.mock()

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

        # 게스트 토큰은 거부한다 (REST와 같은 판정)
        return ensure_member(CurrentUser.from_claims(claims))
    except Exception as e:
        logger.error(f"WebSocket token verification failed: {e}")
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Token verification failed"
        )


async def get_ws_current_user(websocket: WebSocket) -> CurrentUser:
    """
    FastAPI Dependency: WebSocket용 현재 인증된 사용자 반환

    REST의 get_current_user와 동일한 역할.
    테스트 시 app.dependency_overrides로 override 가능.

    인증에 실패하면 연결을 수락한 뒤 1008로 닫는다.
    수락 전에 닫으면 핸드셰이크가 HTTP 403으로 거부되어 브라우저에는 1006으로 보인다.
    """
    try:
        return await authenticate_websocket(websocket)
    except WebSocketException:
        await websocket.accept(subprotocol=get_websocket_subprotocol(websocket))
        raise  # Starlette가 수락된 소켓을 예외의 code·reason으로 닫는다


async def get_ws_active_user(
        websocket: WebSocket,
        current_user: CurrentUser = Depends(get_ws_current_user),
) -> CurrentUser:
    """
    FastAPI Dependency: 탈퇴를 신청했거나 파기한 계정이면 연결을 수락한 뒤 1008로 닫는다
    """
    from app.db.session import get_db
    from app.domain.user.service import AccountState, account_state

    session_gen = get_db()
    try:
        state = account_state(next(session_gen), current_user.sub)
    finally:
        session_gen.close()
    if state != AccountState.ACTIVE:
        await websocket.accept(subprotocol=get_websocket_subprotocol(websocket))
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Account not active")
    return current_user


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
