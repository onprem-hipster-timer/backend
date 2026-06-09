"""
DatabaseKeepAliveTask 테스트

DB keep-alive 백그라운드 태스크의 활성화 조건, 주기적 ping,
실패 내성, 정상 종료(cancel) 동작을 검증한다.
"""
import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings
from app.db.keepalive import DatabaseKeepAliveTask


class TestEnabled:
    """enabled 속성 / 비활성화 조건"""

    def test_positive_interval_enabled(self):
        assert DatabaseKeepAliveTask(interval_seconds=10).enabled is True

    def test_zero_interval_disabled(self):
        assert DatabaseKeepAliveTask(interval_seconds=0).enabled is False

    def test_negative_interval_disabled(self):
        """0 이하(음수)면 비활성화"""
        assert DatabaseKeepAliveTask(interval_seconds=-5).enabled is False

    def test_default_interval_from_settings(self):
        """생성자에 인자가 없으면 설정값을 사용"""
        task = DatabaseKeepAliveTask()
        assert task.interval_seconds == settings.DB_KEEPALIVE_INTERVAL_SECONDS


@pytest.mark.asyncio
async def test_run_disabled_returns_immediately():
    """비활성화 시 run()은 즉시 종료하고 ping하지 않는다."""
    task = DatabaseKeepAliveTask(interval_seconds=0)
    task._ping = AsyncMock()

    await asyncio.wait_for(task.run(), timeout=1.0)

    task._ping.assert_not_called()
    assert task.is_running is False


@pytest.mark.asyncio
async def test_run_pings_periodically():
    """활성화 시 주기적으로 ping을 수행한다."""
    task = DatabaseKeepAliveTask(interval_seconds=0.01)
    task._ping = AsyncMock()

    runner = asyncio.create_task(task.run())
    await asyncio.sleep(0.05)  # 여러 주기가 지나도록 대기
    runner.cancel()
    with pytest.raises(asyncio.CancelledError):
        await runner

    assert task._ping.call_count >= 1


@pytest.mark.asyncio
async def test_run_cancellation_stops_cleanly():
    """cancel 시 CancelledError를 재전파하고 is_running=False가 된다."""
    task = DatabaseKeepAliveTask(interval_seconds=10)
    task._ping = AsyncMock()

    runner = asyncio.create_task(task.run())
    await asyncio.sleep(0.01)  # 태스크가 시작되도록
    assert task.is_running is True

    runner.cancel()
    with pytest.raises(asyncio.CancelledError):
        await runner

    assert task.is_running is False


@pytest.mark.asyncio
async def test_ping_failure_does_not_stop_task():
    """ping 실패가 발생해도 태스크는 계속 동작한다(다음 주기 재시도)."""
    task = DatabaseKeepAliveTask(interval_seconds=0.01)
    task._ping = AsyncMock(side_effect=RuntimeError("transient DB error"))

    runner = asyncio.create_task(task.run())
    await asyncio.sleep(0.05)

    assert task.is_running is True  # 실패에도 계속 실행 중
    assert task._ping.call_count >= 1

    runner.cancel()
    with pytest.raises(asyncio.CancelledError):
        await runner


@pytest.mark.asyncio
async def test_ping_executes_select_1():
    """_ping은 세션에서 SELECT 1을 실행한다."""
    mock_session = AsyncMock()

    @asynccontextmanager
    async def fake_get_async_db():
        yield mock_session

    with patch("app.db.keepalive.get_async_db", fake_get_async_db):
        task = DatabaseKeepAliveTask(interval_seconds=10)
        await task._ping()

    mock_session.execute.assert_awaited_once()
    executed = mock_session.execute.call_args[0][0]
    assert str(executed) == "SELECT 1"
