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
    - Sec-WebSocket-Protocol: authorization.bearer.<jwt>
    - 쿼리 파라미터: timezone=Asia/Seoul (선택, 타임존 설정)

    보안:
    - 토큰은 반드시 Sec-WebSocket-Protocol 헤더로 전달해야 합니다.
    - 쿼리 파라미터를 통한 토큰 전달은 보안상 지원하지 않습니다.

    메시지 프로토콜:
    - 클라이언트 -> 서버: { "type": "timer.create|pause|resume|stop|sync", "payload": {...} }
    - 서버 -> 클라이언트: { "type": "timer.created|updated|sync_result|error", "payload": {...} }

    기능:
    - 타이머 생성/일시정지/재개/종료
    - 동일 사용자 멀티 기기 동기화
    - 친구에게 타이머 활동 알림
    - 타임존 지원 (timezone 쿼리 파라미터)

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

    # 타임존 파라미터 추출
    timezone_str = websocket.query_params.get("timezone")
    tz_obj = None
    if timezone_str:
        try:
            from app.domain.dateutil.service import parse_timezone
            tz_obj = parse_timezone(timezone_str)
            logger.info(f"WebSocket timezone set: {timezone_str} for user {current_user.sub}")
        except Exception as e:
            logger.warning(f"Invalid timezone parameter: {timezone_str}, error: {e}")
            # 잘못된 타임존은 무시하고 UTC 사용

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

    # 활성 타이머 자동 동기화 (항상 수행)
    with _session_manager.get_session() as session:
        try:
            from app.domain.timer.service import TimerService
            from app.domain.timer.schema.ws import TimerData, TimerWSMessageType

            timer_service = TimerService(session, current_user)
            active_timers = timer_service.get_all_timers(status=["RUNNING", "PAUSED"])

            # 타임존 변환 적용
            timer_list = []
            for t in active_timers:
                timer_data = TimerData.model_validate(t)
                if tz_obj:
                    timer_data = timer_data.to_timezone(tz_obj)
                timer_list.append(timer_data)

            sync_msg = WSServerMessage(
                type=TimerWSMessageType.SYNC_RESULT.value,
                payload={
                    "timers": [t.model_dump(mode="json") for t in timer_list],
                    "count": len(timer_list),
                },
                from_user=current_user.sub,
            )
            await connection_manager.send_to_websocket(websocket, sync_msg)
            logger.info(f"Auto-synced {len(timer_list)} active timers for user {current_user.sub}")
        except Exception as e:
            logger.error(f"Auto-sync failed: {e}")
            # 자동 동기화 실패는 치명적이지 않으므로 연결은 유지

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
                    handler = TimerWSHandler(session, current_user, tz_obj)
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
