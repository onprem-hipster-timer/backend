"""
Rate Limit Storage 테스트
"""
import asyncio

import pytest

from app.ratelimit.storage.memory import InMemoryStorage, reset_storage

pytestmark = pytest.mark.ratelimit


@pytest.fixture
def storage():
    """테스트용 저장소"""
    reset_storage()
    return InMemoryStorage()


@pytest.mark.asyncio
async def test_record_request_allowed(storage):
    """정상 요청 허용 테스트"""
    result = await storage.record_request(
        key="test:user1",
        window_seconds=60,
        max_requests=10,
    )

    assert result.allowed is True
    assert result.current_count == 1
    assert result.max_requests == 10
    assert result.remaining == 9
    assert result.reset_after > 0


@pytest.mark.asyncio
async def test_record_request_exceeded(storage):
    """한도 초과 테스트"""
    # 한도까지 요청
    for i in range(5):
        result = await storage.record_request(
            key="test:user1",
            window_seconds=60,
            max_requests=5,
        )
        assert result.allowed is True
        assert result.current_count == i + 1

    # 한도 초과 요청
    result = await storage.record_request(
        key="test:user1",
        window_seconds=60,
        max_requests=5,
    )

    assert result.allowed is False
    assert result.current_count == 5
    assert result.remaining == 0
    assert result.reset_after > 0


@pytest.mark.asyncio
async def test_different_users_independent(storage):
    """사용자별 독립 카운트 테스트"""
    # 사용자1 요청
    result1 = await storage.record_request(
        key="test:user1",
        window_seconds=60,
        max_requests=10,
    )
    assert result1.current_count == 1

    # 사용자2 요청
    result2 = await storage.record_request(
        key="test:user2",
        window_seconds=60,
        max_requests=10,
    )
    assert result2.current_count == 1

    # 사용자1 추가 요청
    result3 = await storage.record_request(
        key="test:user1",
        window_seconds=60,
        max_requests=10,
    )
    assert result3.current_count == 2

    # 사용자2는 여전히 1개
    count = await storage.get_current_count("test:user2", 60)
    assert count == 1


@pytest.mark.asyncio
async def test_reset_key(storage):
    """키 초기화 테스트"""
    # 요청 기록
    await storage.record_request(
        key="test:user1",
        window_seconds=60,
        max_requests=10,
    )

    count = await storage.get_current_count("test:user1", 60)
    assert count == 1

    # 초기화
    await storage.reset("test:user1")

    count = await storage.get_current_count("test:user1", 60)
    assert count == 0


@pytest.mark.asyncio
async def test_cleanup_expired(storage):
    """만료된 엔트리 정리 테스트"""
    # 요청 기록
    await storage.record_request(
        key="test:user1",
        window_seconds=1,
        max_requests=10,
    )

    # 잠시 대기 후 정리
    await asyncio.sleep(0.1)

    cleaned = await storage.cleanup_expired()
    # 아직 만료되지 않았으므로 정리되지 않음
    assert cleaned == 0


@pytest.mark.asyncio
async def test_sliding_window_behavior(storage):
    """슬라이딩 윈도우 동작 테스트"""
    # 짧은 윈도우로 테스트
    window = 1  # 1초 윈도우

    # 한도까지 요청
    for _ in range(3):
        await storage.record_request(
            key="test:user1",
            window_seconds=window,
            max_requests=3,
        )

    # 한도 초과
    result = await storage.record_request(
        key="test:user1",
        window_seconds=window,
        max_requests=3,
    )
    assert result.allowed is False

    # 윈도우 만료 대기
    await asyncio.sleep(1.1)

    # 다시 허용
    result = await storage.record_request(
        key="test:user1",
        window_seconds=window,
        max_requests=3,
    )
    assert result.allowed is True
    assert result.current_count == 1
