"""
WebSocket 타이머 이벤트 핸들러

타이머 생성, 일시정지, 재개, 종료 이벤트 처리
"""
import logging
from datetime import datetime, UTC
from typing import Optional
from uuid import UUID

from fastapi import WebSocket
from sqlmodel import Session

from app.core.auth import CurrentUser
from app.core.constants import TimerStatus
from app.crud import friendship as friendship_crud
from app.domain.timer.schema.dto import TimerCreate
from app.domain.timer.service import TimerService
from app.websocket.manager import connection_manager
from app.websocket.schemas import (
    WSMessageType,
    WSServerMessage,
    TimerAction,
    TimerData,
    TimerCreatePayload,
    TimerActionPayload,
)

logger = logging.getLogger(__name__)


class TimerEventHandler:
    """
    타이머 WebSocket 이벤트 핸들러

    모든 타이머 이벤트를 처리하고 관련 사용자들에게 브로드캐스트합니다.
    """

    def __init__(self, session: Session, current_user: CurrentUser):
        self.session = session
        self.current_user = current_user
        self.timer_service = TimerService(session, current_user)

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

            # 타이머 생성 (status=RUNNING, started_at=now)
            timer = self.timer_service.create_timer(timer_create)

            # pause_history에 start 이벤트 추가
            now = datetime.now(UTC).replace(tzinfo=None)
            timer.pause_history = [
                {"action": "start", "at": now.isoformat()}
            ]
            self.session.flush()
            self.session.refresh(timer)

            # TimerData로 변환
            timer_data = TimerData.model_validate(timer)

            # 응답 메시지 생성
            response = WSServerMessage(
                type=WSMessageType.TIMER_CREATED,
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
            timer = self.timer_service.pause_timer(action_payload.timer_id)

            # pause_history에 pause 이벤트 추가
            now = datetime.now(UTC).replace(tzinfo=None)
            history = list(timer.pause_history) if timer.pause_history else []
            history.append({
                "action": "pause",
                "at": now.isoformat(),
                "elapsed": timer.elapsed_time,
            })
            timer.pause_history = history
            self.session.flush()
            self.session.refresh(timer)

            # TimerData로 변환
            timer_data = TimerData.model_validate(timer)

            # 응답 메시지 생성
            response = WSServerMessage(
                type=WSMessageType.TIMER_UPDATED,
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
            timer = self.timer_service.resume_timer(action_payload.timer_id)

            # pause_history에 resume 이벤트 추가
            now = datetime.now(UTC).replace(tzinfo=None)
            history = list(timer.pause_history) if timer.pause_history else []
            history.append({
                "action": "resume",
                "at": now.isoformat(),
            })
            timer.pause_history = history
            self.session.flush()
            self.session.refresh(timer)

            # TimerData로 변환
            timer_data = TimerData.model_validate(timer)

            # 응답 메시지 생성
            response = WSServerMessage(
                type=WSMessageType.TIMER_UPDATED,
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
            timer = self.timer_service.stop_timer(action_payload.timer_id)

            # pause_history에 stop 이벤트 추가
            now = datetime.now(UTC).replace(tzinfo=None)
            history = list(timer.pause_history) if timer.pause_history else []
            history.append({
                "action": "stop",
                "at": now.isoformat(),
                "elapsed": timer.elapsed_time,
            })
            timer.pause_history = history
            self.session.flush()
            self.session.refresh(timer)

            # TimerData로 변환
            timer_data = TimerData.model_validate(timer)

            # 응답 메시지 생성
            response = WSServerMessage(
                type=WSMessageType.TIMER_UPDATED,
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

        현재 활성 타이머 또는 특정 타이머 정보 반환

        :param payload: TimerSyncPayload 데이터
        :param websocket: 발신 WebSocket
        :return: 응답 메시지
        """
        try:
            timer_id = payload.get("timer_id")

            if timer_id:
                # 특정 타이머 조회
                timer = self.timer_service.get_timer(UUID(timer_id))
            else:
                # 활성 타이머 조회
                timer = self.timer_service.get_user_active_timer()

            if timer:
                timer_data = TimerData.model_validate(timer)
                return WSServerMessage(
                    type=WSMessageType.TIMER_UPDATED,
                    payload={"timer": timer_data.model_dump(mode="json"), "action": "sync"},
                    from_user=self.current_user.sub,
                )
            else:
                return WSServerMessage(
                    type=WSMessageType.TIMER_UPDATED,
                    payload={"timer": None, "action": "sync"},
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
                type=WSMessageType.TIMER_FRIEND_ACTIVITY,
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
