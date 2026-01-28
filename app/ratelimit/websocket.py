"""
WebSocket Rate Limiter

WebSocket 연결 및 메시지에 대한 레이트 리밋 구현
"""
import logging
from dataclasses import dataclass
from typing import Optional

from fastapi import WebSocket

from app.core import config as app_config
from app.ratelimit.storage.base import RateLimitResult
from app.ratelimit.storage.memory import get_storage

logger = logging.getLogger(__name__)


@dataclass
class WSRateLimitConfig:
    """WebSocket 레이트 리밋 설정"""
    connect_window: int  # 연결 제한 윈도우 (초)
    connect_max: int  # 윈도우 내 최대 연결 횟수
    message_window: int  # 메시지 제한 윈도우 (초)
    message_max: int  # 윈도우 내 최대 메시지 수


def get_ws_rate_limit_config() -> WSRateLimitConfig:
    """현재 설정에서 WebSocket 레이트 리밋 설정 가져오기"""
    return WSRateLimitConfig(
        connect_window=app_config.settings.WS_CONNECT_WINDOW,
        connect_max=app_config.settings.WS_CONNECT_MAX,
        message_window=app_config.settings.WS_MESSAGE_WINDOW,
        message_max=app_config.settings.WS_MESSAGE_MAX,
    )


class WebSocketRateLimiter:
    """
    WebSocket 레이트 리미터
    
    두 가지 유형의 제한:
    1. 연결 제한: 동일 사용자가 짧은 시간 내에 반복 연결하는 것 방지
    2. 메시지 제한: 연결 당 메시지 폭주 방지
    """

    def __init__(self):
        self._storage = get_storage()

    async def check_connection(self, user_id: str) -> RateLimitResult:
        """
        연결 레이트 리밋 체크 (연결 전 호출)
        
        :param user_id: 사용자 식별자
        :return: 레이트 리밋 결과
        """
        config = get_ws_rate_limit_config()
        key = f"ws:connect:{user_id}"
        
        return await self._storage.record_request(
            key=key,
            window_seconds=config.connect_window,
            max_requests=config.connect_max,
        )

    async def check_message(self, user_id: str) -> RateLimitResult:
        """
        메시지 레이트 리밋 체크 (메시지 수신 시 호출)
        
        :param user_id: 사용자 식별자
        :return: 레이트 리밋 결과
        """
        config = get_ws_rate_limit_config()
        key = f"ws:message:{user_id}"
        
        return await self._storage.record_request(
            key=key,
            window_seconds=config.message_window,
            max_requests=config.message_max,
        )

    async def get_connection_remaining(self, user_id: str) -> int:
        """
        남은 연결 가능 횟수 조회
        
        :param user_id: 사용자 식별자
        :return: 남은 연결 횟수
        """
        config = get_ws_rate_limit_config()
        key = f"ws:connect:{user_id}"
        current = await self._storage.get_current_count(key, config.connect_window)
        return max(0, config.connect_max - current)

    async def get_message_remaining(self, user_id: str) -> int:
        """
        남은 메시지 전송 가능 횟수 조회
        
        :param user_id: 사용자 식별자
        :return: 남은 메시지 수
        """
        config = get_ws_rate_limit_config()
        key = f"ws:message:{user_id}"
        current = await self._storage.get_current_count(key, config.message_window)
        return max(0, config.message_max - current)

    async def reset_user(self, user_id: str) -> None:
        """
        사용자의 모든 WebSocket 레이트 리밋 초기화
        
        :param user_id: 사용자 식별자
        """
        await self._storage.reset(f"ws:connect:{user_id}")
        await self._storage.reset(f"ws:message:{user_id}")


# 싱글톤 인스턴스
_ws_limiter_instance: Optional[WebSocketRateLimiter] = None


def get_ws_limiter() -> WebSocketRateLimiter:
    """WebSocket 레이트 리미터 싱글톤 인스턴스 반환"""
    global _ws_limiter_instance
    if _ws_limiter_instance is None:
        _ws_limiter_instance = WebSocketRateLimiter()
    return _ws_limiter_instance


def reset_ws_limiter() -> None:
    """WebSocket 레이트 리미터 인스턴스 초기화 (테스트용)"""
    global _ws_limiter_instance
    _ws_limiter_instance = None


async def ws_rate_limit_guard(
        websocket: WebSocket,
        user_id: str,
        check_type: str = "message",
) -> tuple[bool, Optional[str]]:
    """
    WebSocket 레이트 리밋 가드 함수
    
    :param websocket: WebSocket 연결
    :param user_id: 사용자 식별자
    :param check_type: 체크 유형 ("connect" 또는 "message")
    :return: (허용 여부, 에러 메시지 또는 None)
    """
    if not app_config.settings.WS_RATE_LIMIT_ENABLED:
        return True, None

    limiter = get_ws_limiter()

    if check_type == "connect":
        result = await limiter.check_connection(user_id)
        limit_type = "연결"
    else:
        result = await limiter.check_message(user_id)
        limit_type = "메시지"

    if not result.allowed:
        logger.warning(
            f"WebSocket rate limit exceeded: user={user_id}, type={check_type}, "
            f"count={result.current_count}/{result.max_requests}"
        )
        return False, (
            f"WebSocket {limit_type} 한도를 초과했습니다. "
            f"{result.reset_after}초 후에 다시 시도해주세요."
        )

    return True, None
