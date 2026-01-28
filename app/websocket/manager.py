"""
WebSocket 연결 관리자

사용자별 연결 관리 및 브로드캐스트 기능 제공
"""
import asyncio
import logging
from typing import Optional

from fastapi import WebSocket

from app.websocket.base import WSServerMessage

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    WebSocket 연결 관리자

    기능:
    - 사용자별 다중 연결 관리 (멀티 플랫폼 지원)
    - 사용자 전체 연결 브로드캐스트
    - 친구 그룹 브로드캐스트
    """

    def __init__(self):
        # 사용자 ID -> 연결 목록 매핑
        # 한 사용자가 여러 기기에서 접속 가능
        self._connections: dict[str, list[WebSocket]] = {}
        # 연결 -> 사용자 ID 역매핑 (빠른 조회용)
        self._user_by_connection: dict[WebSocket, str] = {}
        # 비동기 락 (동시성 제어)
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, user_id: str) -> None:
        """
        새 WebSocket 연결 등록

        :param websocket: WebSocket 인스턴스
        :param user_id: 사용자 ID (OIDC sub claim)
        """
        async with self._lock:
            if user_id not in self._connections:
                self._connections[user_id] = []

            self._connections[user_id].append(websocket)
            self._user_by_connection[websocket] = user_id

            logger.info(
                f"WebSocket connected: user={user_id}, "
                f"total_connections={len(self._connections[user_id])}"
            )

    async def disconnect(self, websocket: WebSocket) -> Optional[str]:
        """
        WebSocket 연결 해제

        :param websocket: WebSocket 인스턴스
        :return: 연결 해제된 사용자 ID
        """
        async with self._lock:
            user_id = self._user_by_connection.pop(websocket, None)

            if user_id and user_id in self._connections:
                try:
                    self._connections[user_id].remove(websocket)
                except ValueError:
                    pass

                # 사용자의 모든 연결이 해제되면 목록 제거
                if not self._connections[user_id]:
                    del self._connections[user_id]

                logger.info(f"WebSocket disconnected: user={user_id}")

            return user_id

    async def send_to_user(
            self,
            user_id: str,
            message: WSServerMessage,
            exclude_websocket: Optional[WebSocket] = None,
    ) -> int:
        """
        특정 사용자의 모든 연결에 메시지 전송

        :param user_id: 대상 사용자 ID
        :param message: 전송할 메시지
        :param exclude_websocket: 제외할 연결 (발신자 본인 제외용)
        :return: 전송 성공한 연결 수
        """
        async with self._lock:
            connections = self._connections.get(user_id, []).copy()

        sent_count = 0
        for ws in connections:
            if ws == exclude_websocket:
                continue

            try:
                await ws.send_text(message.to_json())
                sent_count += 1
            except Exception as e:
                logger.warning(f"Failed to send to user {user_id}: {e}")
                # 실패한 연결은 disconnect에서 정리됨

        return sent_count

    async def send_to_websocket(
            self,
            websocket: WebSocket,
            message: WSServerMessage,
    ) -> bool:
        """
        특정 WebSocket 연결에 메시지 전송

        :param websocket: 대상 WebSocket
        :param message: 전송할 메시지
        :return: 전송 성공 여부
        """
        try:
            await websocket.send_text(message.to_json())
            return True
        except Exception as e:
            logger.warning(f"Failed to send message: {e}")
            return False

    async def broadcast_to_friends(
            self,
            friend_ids: list[str],
            message: WSServerMessage,
    ) -> int:
        """
        친구들에게 메시지 브로드캐스트

        :param friend_ids: 친구 ID 목록
        :param message: 전송할 메시지
        :return: 전송 성공한 총 연결 수
        """
        total_sent = 0
        for friend_id in friend_ids:
            sent = await self.send_to_user(friend_id, message)
            total_sent += sent

        return total_sent

    def get_user_connection_count(self, user_id: str) -> int:
        """사용자의 현재 연결 수 반환"""
        return len(self._connections.get(user_id, []))

    def get_total_connections(self) -> int:
        """전체 연결 수 반환"""
        return len(self._user_by_connection)

    def get_online_users(self) -> list[str]:
        """현재 온라인 사용자 목록 반환"""
        return list(self._connections.keys())

    def is_user_online(self, user_id: str) -> bool:
        """사용자가 온라인인지 확인"""
        return user_id in self._connections and len(self._connections[user_id]) > 0


# 전역 싱글톤 인스턴스
connection_manager = ConnectionManager()
