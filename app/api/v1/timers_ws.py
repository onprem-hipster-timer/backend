"""
타이머 WebSocket 라우터

타이머 실시간 동기화 WebSocket 엔드포인트
- /ws/timers: 타이머 생성, 일시정지, 재개, 종료
"""
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.db.session import _session_manager
from app.domain.timer.ws_handler import TimerWSHandler
from app.ratelimit.websocket import ws_rate_limit_guard
from app.websocket.auth import authenticate_websocket, get_websocket_subprotocol
from app.websocket.base import WSClientMessage, WSServerMessage, WSMessageType
from app.websocket.manager import connection_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Timer WebSocket"])


@router.websocket("/ws/timers")
async def timer_websocket(websocket: WebSocket):
    """
    타이머 실시간 동기화 WebSocket 엔드포인트

    연결 방법:
    1. 쿼리 파라미터: ws://host/ws/timers?token=<jwt>
    2. Sec-WebSocket-Protocol: authorization.bearer.<jwt>

    메시지 프로토콜:
    - 클라이언트 -> 서버: { "type": "timer.create|pause|resume|stop|sync", "payload": {...} }
    - 서버 -> 클라이언트: { "type": "timer.created|updated|error", "payload": {...} }

    기능:
    - 타이머 생성/일시정지/재개/종료
    - 동일 사용자 멀티 기기 동기화
    - 친구에게 타이머 활동 알림

    Rate Limit:
    - 연결: WS_CONNECT_MAX 회/WS_CONNECT_WINDOW 초 (기본 10회/60초)
    - 메시지: WS_MESSAGE_MAX 개/WS_MESSAGE_WINDOW 초 (기본 120개/60초)
    """
    # 인증
    try:
        current_user = await authenticate_websocket(websocket)
    except Exception as e:
        logger.warning(f"WebSocket authentication failed: {e}")
        await websocket.close(code=4001, reason="Authentication failed")
        return

    # 연결 Rate Limit 체크 (인증 후, 연결 수락 전)
    allowed, error_message = await ws_rate_limit_guard(
        websocket, current_user.sub, check_type="connect"
    )
    if not allowed:
        logger.warning(f"WebSocket connection rate limit: user={current_user.sub}")
        await websocket.close(code=4029, reason=error_message or "Connection rate limit exceeded")
        return

    # 서브프로토콜 확인 (Sec-WebSocket-Protocol 응답용)
    subprotocol = get_websocket_subprotocol(websocket)

    # WebSocket 연결 수락
    await websocket.accept(subprotocol=subprotocol)

    # 연결 등록
    await connection_manager.connect(websocket, current_user.sub)

    # 연결 성공 메시지 전송
    connected_msg = WSServerMessage(
        type=WSMessageType.CONNECTED,
        payload={
            "user_id": current_user.sub,
            "message": "Connected to timer WebSocket",
        },
        from_user=current_user.sub,
    )
    await connection_manager.send_to_websocket(websocket, connected_msg)

    try:
        while True:
            # 메시지 수신
            data = await websocket.receive_text()

            # 메시지 Rate Limit 체크
            allowed, error_message = await ws_rate_limit_guard(
                websocket, current_user.sub, check_type="message"
            )
            if not allowed:
                rate_limit_msg = WSServerMessage(
                    type=WSMessageType.ERROR,
                    payload={
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": error_message or "Message rate limit exceeded",
                    },
                )
                await connection_manager.send_to_websocket(websocket, rate_limit_msg)
                continue

            try:
                message_data = json.loads(data)
                client_message = WSClientMessage(**message_data)
            except (json.JSONDecodeError, ValueError) as e:
                error_msg = WSServerMessage(
                    type=WSMessageType.ERROR,
                    payload={
                        "code": "INVALID_MESSAGE",
                        "message": f"Invalid message format: {e}",
                    },
                )
                await connection_manager.send_to_websocket(websocket, error_msg)
                continue

            # 타이머 도메인 핸들러로 디스패치
            with _session_manager.get_session() as session:
                try:
                    handler = TimerWSHandler(session, current_user)
                    response = await handler.dispatch(client_message, websocket)

                    if response:
                        await connection_manager.send_to_websocket(websocket, response)

                    # 트랜잭션 커밋
                    session.commit()

                except Exception as e:
                    session.rollback()
                    logger.error(f"Error handling WebSocket message: {e}")
                    error_msg = WSServerMessage(
                        type=WSMessageType.ERROR,
                        payload={
                            "code": "HANDLER_ERROR",
                            "message": str(e),
                        },
                    )
                    await connection_manager.send_to_websocket(websocket, error_msg)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: user={current_user.sub}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        # 연결 해제
        await connection_manager.disconnect(websocket)
