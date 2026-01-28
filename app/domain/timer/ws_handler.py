"""
타이머 WebSocket 이벤트 핸들러

Timer 도메인의 WebSocket 처리 로직
- TimerService를 통해 비즈니스 로직 수행
- 동일 사용자 멀티 디바이스 동기화
- 친구에게 활동 알림
"""
import logging
from typing import Optional
from uuid import UUID

from fastapi import WebSocket
from sqlmodel import Session

from app.core.auth import CurrentUser
from app.crud import friendship as friendship_crud
from app.domain.timer.schema.dto import TimerCreate
from app.domain.timer.schema.ws import (
    TimerWSMessageType,
    TimerAction,
    TimerCreatePayload,
    TimerActionPayload,
    TimerData,
)
from app.domain.timer.service import TimerService
from app.websocket.base import WSClientMessage, WSServerMessage, WSMessageType
from app.websocket.manager import connection_manager

logger = logging.getLogger(__name__)


class TimerWSHandler:
    """
    타이머 WebSocket 이벤트 핸들러

    모든 타이머 이벤트를 처리하고 관련 사용자들에게 브로드캐스트합니다.
    
    Note: pause_history는 TimerService에서 처리하므로 핸들러에서는 
    Service 메서드 호출만 수행합니다.
    """

    def __init__(self, session: Session, current_user: CurrentUser, tz=None):
        self.session = session
        self.current_user = current_user
        self.timer_service = TimerService(session, current_user)
        self.tz = tz  # 타임존 (timezone 객체, 문자열, 또는 None)

    async def dispatch(
        self,
        message: WSClientMessage,
        websocket: WebSocket,
    ) -> Optional[WSServerMessage]:
        """
        메시지 타입별 핸들러 디스패치
        
        :param message: 클라이언트 메시지
        :param websocket: 발신 WebSocket
        :return: 응답 메시지
        """
        handlers = {
            TimerWSMessageType.CREATE.value: self.handle_create,
            TimerWSMessageType.PAUSE.value: self.handle_pause,
            TimerWSMessageType.RESUME.value: self.handle_resume,
            TimerWSMessageType.STOP.value: self.handle_stop,
            TimerWSMessageType.SYNC.value: self.handle_sync,
        }

        handler = handlers.get(message.type)
        if handler:
            return await handler(message.payload, websocket)

        return WSServerMessage(
            type=WSMessageType.ERROR,
            payload={"code": "UNKNOWN_TYPE", "message": f"Unknown message type: {message.type}"},
        )

    async def handle_create(
        self,
        payload: dict,
        websocket: WebSocket,
    ) -> Optional[WSServerMessage]:
        """
        타이머 생성 이벤트 처리

        :param payload: TimerCreatePayload 데이터
        :param websocket: 발신 WebSocket
        :return: 응답 메시지
        """
        try:
            create_payload = TimerCreatePayload(**payload)
            timer_create = TimerCreate(
                schedule_id=create_payload.schedule_id,
                todo_id=create_payload.todo_id,
                title=create_payload.title,
                description=create_payload.description,
                allocated_duration=create_payload.allocated_duration,
                tag_ids=create_payload.tag_ids,
            )

            # 타이머 생성 (TimerService에서 pause_history 처리 포함)
            timer = self.timer_service.create_timer(timer_create)

            # TimerData로 변환 및 타임존 적용
            timer_data = TimerData.model_validate(timer)
            if self.tz:
                timer_data = timer_data.to_timezone(self.tz)

            # 응답 메시지 생성
            response = WSServerMessage(
                type=TimerWSMessageType.CREATED.value,
                payload={"timer": timer_data.model_dump(mode="json"), "action": TimerAction.START.value},
                from_user=self.current_user.sub,
            )

            # 본인의 다른 기기들에 동기화
            await connection_manager.send_to_user(
                self.current_user.sub,
                response,
                exclude_websocket=websocket,
            )

            # 친구들에게 알림
            await self._notify_friends(TimerAction.START, timer.id, timer.title)

            return response

        except Exception as e:
            logger.error(f"Timer create failed: {e}")
            return WSServerMessage(
                type=WSMessageType.ERROR,
                payload={"code": "CREATE_FAILED", "message": str(e)},
            )

    async def handle_pause(
        self,
        payload: dict,
        websocket: WebSocket,
    ) -> Optional[WSServerMessage]:
        """
        타이머 일시정지 이벤트 처리

        :param payload: TimerActionPayload 데이터
        :param websocket: 발신 WebSocket
        :return: 응답 메시지
        """
        try:
            action_payload = TimerActionPayload(**payload)
            
            # TimerService에서 pause_history 처리 포함
            timer = self.timer_service.pause_timer(action_payload.timer_id)

            # TimerData로 변환 및 타임존 적용
            timer_data = TimerData.model_validate(timer)
            if self.tz:
                timer_data = timer_data.to_timezone(self.tz)

            # 응답 메시지 생성
            response = WSServerMessage(
                type=TimerWSMessageType.UPDATED.value,
                payload={"timer": timer_data.model_dump(mode="json"), "action": TimerAction.PAUSE.value},
                from_user=self.current_user.sub,
            )

            # 본인의 다른 기기들에 동기화
            await connection_manager.send_to_user(
                self.current_user.sub,
                response,
                exclude_websocket=websocket,
            )

            # 친구들에게 알림
            await self._notify_friends(TimerAction.PAUSE, timer.id, timer.title)

            return response

        except Exception as e:
            logger.error(f"Timer pause failed: {e}")
            return WSServerMessage(
                type=WSMessageType.ERROR,
                payload={"code": "PAUSE_FAILED", "message": str(e)},
            )

    async def handle_resume(
        self,
        payload: dict,
        websocket: WebSocket,
    ) -> Optional[WSServerMessage]:
        """
        타이머 재개 이벤트 처리

        :param payload: TimerActionPayload 데이터
        :param websocket: 발신 WebSocket
        :return: 응답 메시지
        """
        try:
            action_payload = TimerActionPayload(**payload)
            
            # TimerService에서 pause_history 처리 포함
            timer = self.timer_service.resume_timer(action_payload.timer_id)

            # TimerData로 변환 및 타임존 적용
            timer_data = TimerData.model_validate(timer)
            if self.tz:
                timer_data = timer_data.to_timezone(self.tz)

            # 응답 메시지 생성
            response = WSServerMessage(
                type=TimerWSMessageType.UPDATED.value,
                payload={"timer": timer_data.model_dump(mode="json"), "action": TimerAction.RESUME.value},
                from_user=self.current_user.sub,
            )

            # 본인의 다른 기기들에 동기화
            await connection_manager.send_to_user(
                self.current_user.sub,
                response,
                exclude_websocket=websocket,
            )

            # 친구들에게 알림
            await self._notify_friends(TimerAction.RESUME, timer.id, timer.title)

            return response

        except Exception as e:
            logger.error(f"Timer resume failed: {e}")
            return WSServerMessage(
                type=WSMessageType.ERROR,
                payload={"code": "RESUME_FAILED", "message": str(e)},
            )

    async def handle_stop(
        self,
        payload: dict,
        websocket: WebSocket,
    ) -> Optional[WSServerMessage]:
        """
        타이머 종료 이벤트 처리

        :param payload: TimerActionPayload 데이터
        :param websocket: 발신 WebSocket
        :return: 응답 메시지
        """
        try:
            action_payload = TimerActionPayload(**payload)
            
            # TimerService에서 pause_history 처리 포함
            timer = self.timer_service.stop_timer(action_payload.timer_id)

            # TimerData로 변환 및 타임존 적용
            timer_data = TimerData.model_validate(timer)
            if self.tz:
                timer_data = timer_data.to_timezone(self.tz)

            # 응답 메시지 생성
            response = WSServerMessage(
                type=TimerWSMessageType.UPDATED.value,
                payload={"timer": timer_data.model_dump(mode="json"), "action": TimerAction.STOP.value},
                from_user=self.current_user.sub,
            )

            # 본인의 다른 기기들에 동기화
            await connection_manager.send_to_user(
                self.current_user.sub,
                response,
                exclude_websocket=websocket,
            )

            # 친구들에게 알림
            await self._notify_friends(TimerAction.STOP, timer.id, timer.title)

            return response

        except Exception as e:
            logger.error(f"Timer stop failed: {e}")
            return WSServerMessage(
                type=WSMessageType.ERROR,
                payload={"code": "STOP_FAILED", "message": str(e)},
            )

    async def handle_sync(
        self,
        payload: dict,
        websocket: WebSocket,
    ) -> Optional[WSServerMessage]:
        """
        타이머 동기화 요청 처리

        특정 타이머 조회 또는 활성 타이머 목록 반환

        :param payload: TimerSyncPayload 데이터
        :param websocket: 발신 WebSocket
        :return: 응답 메시지
        """
        try:
            timer_id = payload.get("timer_id")
            scope = payload.get("scope", "active")

            if timer_id:
                # 특정 타이머 조회 (단건)
                timer = self.timer_service.get_timer(UUID(timer_id))
                if timer:
                    timer_data = TimerData.model_validate(timer)
                    if self.tz:
                        timer_data = timer_data.to_timezone(self.tz)
                    return WSServerMessage(
                        type=TimerWSMessageType.UPDATED.value,
                        payload={"timer": timer_data.model_dump(mode="json"), "action": "sync"},
                        from_user=self.current_user.sub,
                    )
                else:
                    return WSServerMessage(
                        type=TimerWSMessageType.UPDATED.value,
                        payload={"timer": None, "action": "sync"},
                        from_user=self.current_user.sub,
                    )
            else:
                # 타이머 목록 조회
                if scope == "active":
                    timers = self.timer_service.get_all_timers(status=["RUNNING", "PAUSED"])
                else:
                    timers = self.timer_service.get_all_timers()

                # 타임존 변환 적용
                timer_list = []
                for t in timers:
                    timer_data = TimerData.model_validate(t)
                    if self.tz:
                        timer_data = timer_data.to_timezone(self.tz)
                    timer_list.append(timer_data)

                return WSServerMessage(
                    type=TimerWSMessageType.SYNC_RESULT.value,
                    payload={
                        "timers": [t.model_dump(mode="json") for t in timer_list],
                        "count": len(timer_list),
                    },
                    from_user=self.current_user.sub,
                )

        except Exception as e:
            logger.error(f"Timer sync failed: {e}")
            return WSServerMessage(
                type=WSMessageType.ERROR,
                payload={"code": "SYNC_FAILED", "message": str(e)},
            )

    async def _notify_friends(
        self,
        action: TimerAction,
        timer_id: UUID,
        timer_title: Optional[str],
    ) -> None:
        """
        친구들에게 타이머 활동 알림

        :param action: 타이머 액션
        :param timer_id: 타이머 ID
        :param timer_title: 타이머 제목
        """
        try:
            # 친구 ID 목록 조회
            friend_ids = friendship_crud.get_friend_ids(
                self.session,
                self.current_user.sub,
            )

            if not friend_ids:
                return

            # 알림 메시지 생성
            notification = WSServerMessage(
                type=TimerWSMessageType.FRIEND_ACTIVITY.value,
                payload={
                    "friend_id": self.current_user.sub,
                    "action": action.value,
                    "timer_id": str(timer_id),
                    "timer_title": timer_title,
                },
                from_user=self.current_user.sub,
            )

            # 온라인 친구들에게만 전송
            await connection_manager.broadcast_to_friends(friend_ids, notification)

        except Exception as e:
            logger.error(f"Failed to notify friends: {e}")
