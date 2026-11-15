"""
타이머 실시간 WebSocket (수신 전용, REALTIME_BACKEND=inprocess)

- 인증: `Sec-WebSocket-Protocol: authorization.bearer.<jwt>`. 101에 같은 값을 돌려주고, 실패하거나 탈퇴를 신청한 계정이면 1008로 닫는다
- 연결 직후 `connected`를 보낸다. 이후에는 커밋된 타이머 변경의 이벤트 봉투만 보낸다 (app/domain/timer/realtime.py)
- 클라이언트 메시지는 문자열 `ping`뿐이고 서버는 `pong`으로 답한다. 그 외는 무시한다
- 명령은 REST(/v1/timers)로 한다. 클라이언트는 연결·재연결 직후 REST로 상태를 다시 맞춘다

계약: docs/api/websocket.ko.md
테스트: tests/test_websocket_timers.py
"""
import logging

from fastapi import APIRouter, WebSocket, Depends

from app.core.auth import CurrentUser
from app.ratelimit.websocket import ws_rate_limit_guard
from app.websocket.auth import get_ws_active_user, get_websocket_subprotocol
from app.websocket.base import WSServerMessage, WSMessageType
from app.websocket.manager import connection_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Timer WebSocket"])


@router.websocket("/ws/timers")
async def timer_websocket(
        websocket: WebSocket,
        current_user: CurrentUser = Depends(get_ws_active_user),
):
    """
    타이머 실시간 수신 WebSocket

    Rate Limit: 연결 WS_CONNECT_MAX 회/WS_CONNECT_WINDOW 초 (기본 10회/60초). 넘으면 4029로 닫는다
    """
    # 연결 Rate Limit 체크 (인증 후, 연결 수락 전)
    allowed, error_message = await ws_rate_limit_guard(websocket, current_user.sub)
    await websocket.accept(subprotocol=get_websocket_subprotocol(websocket))
    if not allowed:
        # 수락 전에 닫으면 핸드셰이크가 HTTP 403으로 거부되어 브라우저에는 4029가 아닌 1006으로 보인다
        logger.warning(f"WebSocket connection rate limit: user={current_user.sub}")
        await websocket.close(code=4029, reason=error_message or "Connection rate limit exceeded")
        return

    await connection_manager.connect(websocket, current_user.sub)

    try:
        await connection_manager.send_to_websocket(websocket, WSServerMessage(type=WSMessageType.CONNECTED))
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                logger.info(f"WebSocket disconnected: user={current_user.sub}")
                break
            if message.get("text") == "ping":
                await websocket.send_text("pong")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        await connection_manager.disconnect(websocket)
