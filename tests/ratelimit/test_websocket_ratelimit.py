"""
WebSocket Rate Limit 테스트

WebSocket 연결 및 메시지 레이트 리밋 테스트
"""
import os
from unittest.mock import patch, AsyncMock

import pytest

# 테스트 환경 설정
os.environ["OIDC_ENABLED"] = "false"
os.environ["RATE_LIMIT_ENABLED"] = "true"
os.environ["WS_RATE_LIMIT_ENABLED"] = "true"

from app.ratelimit.websocket import (
    get_ws_limiter,
    reset_ws_limiter,
    ws_rate_limit_guard,
    get_ws_rate_limit_config,
)
from app.ratelimit.storage.memory import reset_storage


class TestWebSocketRateLimiter:
    """WebSocket 레이트 리미터 단위 테스트"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """각 테스트 전에 스토리지와 리미터 초기화"""
        reset_storage()
        reset_ws_limiter()
        yield
        reset_storage()
        reset_ws_limiter()

    @pytest.mark.asyncio
    async def test_connection_rate_limit_allowed(self):
        """연결 레이트 리밋 - 허용"""
        limiter = get_ws_limiter()
        user_id = "test-user-1"

        result = await limiter.check_connection(user_id)

        assert result.allowed is True
        assert result.current_count == 1
        assert result.remaining >= 0

    @pytest.mark.asyncio
    async def test_connection_rate_limit_exceeded(self):
        """연결 레이트 리밋 - 초과"""
        limiter = get_ws_limiter()
        user_id = "test-user-2"
        config = get_ws_rate_limit_config()

        # 최대 연결 횟수만큼 연결
        for _ in range(config.connect_max):
            await limiter.check_connection(user_id)

        # 다음 연결은 차단되어야 함
        result = await limiter.check_connection(user_id)

        assert result.allowed is False
        assert result.current_count == config.connect_max

    @pytest.mark.asyncio
    async def test_message_rate_limit_allowed(self):
        """메시지 레이트 리밋 - 허용"""
        limiter = get_ws_limiter()
        user_id = "test-user-3"

        result = await limiter.check_message(user_id)

        assert result.allowed is True
        assert result.current_count == 1

    @pytest.mark.asyncio
    async def test_message_rate_limit_exceeded(self):
        """메시지 레이트 리밋 - 초과"""
        limiter = get_ws_limiter()
        user_id = "test-user-4"
        config = get_ws_rate_limit_config()

        # 최대 메시지 수만큼 전송
        for _ in range(config.message_max):
            await limiter.check_message(user_id)

        # 다음 메시지는 차단되어야 함
        result = await limiter.check_message(user_id)

        assert result.allowed is False

    @pytest.mark.asyncio
    async def test_get_connection_remaining(self):
        """남은 연결 횟수 조회"""
        limiter = get_ws_limiter()
        user_id = "test-user-5"
        config = get_ws_rate_limit_config()

        # 초기 상태
        remaining = await limiter.get_connection_remaining(user_id)
        assert remaining == config.connect_max

        # 연결 후
        await limiter.check_connection(user_id)
        remaining = await limiter.get_connection_remaining(user_id)
        assert remaining == config.connect_max - 1

    @pytest.mark.asyncio
    async def test_get_message_remaining(self):
        """남은 메시지 횟수 조회"""
        limiter = get_ws_limiter()
        user_id = "test-user-6"
        config = get_ws_rate_limit_config()

        # 초기 상태
        remaining = await limiter.get_message_remaining(user_id)
        assert remaining == config.message_max

        # 메시지 후
        await limiter.check_message(user_id)
        remaining = await limiter.get_message_remaining(user_id)
        assert remaining == config.message_max - 1

    @pytest.mark.asyncio
    async def test_reset_user(self):
        """사용자 레이트 리밋 초기화"""
        limiter = get_ws_limiter()
        user_id = "test-user-7"
        config = get_ws_rate_limit_config()

        # 연결 및 메시지 사용
        await limiter.check_connection(user_id)
        await limiter.check_message(user_id)

        # 초기화
        await limiter.reset_user(user_id)

        # 초기화 후 다시 전체 사용 가능
        conn_remaining = await limiter.get_connection_remaining(user_id)
        msg_remaining = await limiter.get_message_remaining(user_id)

        assert conn_remaining == config.connect_max
        assert msg_remaining == config.message_max

    @pytest.mark.asyncio
    async def test_independent_user_limits(self):
        """사용자별 독립적인 레이트 리밋"""
        limiter = get_ws_limiter()
        user_a = "user-a"
        user_b = "user-b"
        config = get_ws_rate_limit_config()

        # user_a의 연결 한도 소진
        for _ in range(config.connect_max):
            await limiter.check_connection(user_a)

        # user_a는 차단, user_b는 허용
        result_a = await limiter.check_connection(user_a)
        result_b = await limiter.check_connection(user_b)

        assert result_a.allowed is False
        assert result_b.allowed is True


class TestWSRateLimitGuard:
    """ws_rate_limit_guard 함수 테스트"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """각 테스트 전에 스토리지와 리미터 초기화"""
        reset_storage()
        reset_ws_limiter()
        yield
        reset_storage()
        reset_ws_limiter()

    @pytest.mark.asyncio
    async def test_guard_allows_connection(self):
        """가드 함수 - 연결 허용"""
        mock_websocket = AsyncMock()
        user_id = "guard-user-1"

        allowed, error = await ws_rate_limit_guard(
            mock_websocket, user_id, check_type="connect"
        )

        assert allowed is True
        assert error is None

    @pytest.mark.asyncio
    async def test_guard_allows_message(self):
        """가드 함수 - 메시지 허용"""
        mock_websocket = AsyncMock()
        user_id = "guard-user-2"

        allowed, error = await ws_rate_limit_guard(
            mock_websocket, user_id, check_type="message"
        )

        assert allowed is True
        assert error is None

    @pytest.mark.asyncio
    async def test_guard_blocks_connection_on_limit(self):
        """가드 함수 - 연결 차단"""
        mock_websocket = AsyncMock()
        user_id = "guard-user-3"
        config = get_ws_rate_limit_config()

        # 한도 소진
        for _ in range(config.connect_max):
            await ws_rate_limit_guard(mock_websocket, user_id, check_type="connect")

        # 다음 연결 차단
        allowed, error = await ws_rate_limit_guard(
            mock_websocket, user_id, check_type="connect"
        )

        assert allowed is False
        assert error is not None
        assert "연결" in error

    @pytest.mark.asyncio
    async def test_guard_blocks_message_on_limit(self):
        """가드 함수 - 메시지 차단"""
        mock_websocket = AsyncMock()
        user_id = "guard-user-4"
        config = get_ws_rate_limit_config()

        # 한도 소진
        for _ in range(config.message_max):
            await ws_rate_limit_guard(mock_websocket, user_id, check_type="message")

        # 다음 메시지 차단
        allowed, error = await ws_rate_limit_guard(
            mock_websocket, user_id, check_type="message"
        )

        assert allowed is False
        assert error is not None
        assert "메시지" in error

    @pytest.mark.asyncio
    async def test_guard_disabled_when_setting_off(self):
        """레이트 리밋 비활성화 시 항상 허용"""
        mock_websocket = AsyncMock()
        user_id = "guard-user-5"

        # 설정을 임시로 비활성화
        with patch("app.ratelimit.websocket.app_config.settings") as mock_settings:
            mock_settings.WS_RATE_LIMIT_ENABLED = False

            # 항상 허용
            allowed, error = await ws_rate_limit_guard(
                mock_websocket, user_id, check_type="connect"
            )

            assert allowed is True
            assert error is None


class TestWSRateLimitConfig:
    """WebSocket 레이트 리밋 설정 테스트"""

    def test_default_config(self):
        """기본 설정 값"""
        config = get_ws_rate_limit_config()

        assert config.connect_window > 0
        assert config.connect_max > 0
        assert config.message_window > 0
        assert config.message_max > 0

    def test_config_from_settings(self):
        """설정에서 값 로드"""
        with patch("app.ratelimit.websocket.app_config.settings") as mock_settings:
            mock_settings.WS_CONNECT_WINDOW = 120
            mock_settings.WS_CONNECT_MAX = 20
            mock_settings.WS_MESSAGE_WINDOW = 30
            mock_settings.WS_MESSAGE_MAX = 60

            config = get_ws_rate_limit_config()

            assert config.connect_window == 120
            assert config.connect_max == 20
            assert config.message_window == 30
            assert config.message_max == 60
