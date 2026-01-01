"""
HolidaySyncGuard 테스트

동기화 중복 방지 및 범위 완료 추적 테스트
"""
import pytest
import asyncio
from unittest.mock import AsyncMock

from app.domain.holiday.sync_guard import HolidaySyncGuard


@pytest.mark.asyncio
async def test_sync_year_single_execution():
    """단일 연도 동기화가 한 번만 실행되는지 테스트"""
    guard = HolidaySyncGuard()
    mock_sync = AsyncMock()
    
    await guard.sync_year(2024, mock_sync)
    
    # 한 번만 호출되어야 함
    assert mock_sync.call_count == 1
    mock_sync.assert_called_once_with(2024)


@pytest.mark.asyncio
async def test_sync_year_duplicate_prevention():
    """동일 연도 중복 실행 방지 테스트"""
    guard = HolidaySyncGuard()
    mock_sync = AsyncMock()
    
    # 첫 번째 호출 시작 (비동기)
    task1 = asyncio.create_task(guard.sync_year(2024, mock_sync))
    
    # 짧은 딜레이 (첫 번째 호출이 시작되도록)
    await asyncio.sleep(0.01)
    
    # 두 번째 호출 (같은 연도)
    task2 = asyncio.create_task(guard.sync_year(2024, mock_sync))
    
    # 두 작업 모두 완료 대기
    await task1
    await task2
    
    # 한 번만 실행되어야 함 (중복 방지)
    assert mock_sync.call_count == 1


@pytest.mark.asyncio
async def test_sync_year_different_years():
    """서로 다른 연도는 독립적으로 실행되는지 테스트"""
    guard = HolidaySyncGuard()
    mock_sync = AsyncMock()
    
    # 두 개의 다른 연도 동시 실행
    await asyncio.gather(
        guard.sync_year(2024, mock_sync),
        guard.sync_year(2025, mock_sync),
    )
    
    # 각각 한 번씩 실행되어야 함
    assert mock_sync.call_count == 2
    assert mock_sync.call_args_list == [
        ((2024,),),
        ((2025,),),
    ]


@pytest.mark.asyncio
async def test_sync_years_range():
    """범위 동기화가 모든 연도를 처리하는지 테스트"""
    guard = HolidaySyncGuard()
    mock_sync = AsyncMock()
    
    await guard.sync_years(2024, 2026, mock_sync)
    
    # 2024, 2025, 2026 각각 한 번씩 호출
    assert mock_sync.call_count == 3
    called_years = [call[0][0] for call in mock_sync.call_args_list]
    assert set(called_years) == {2024, 2025, 2026}


@pytest.mark.asyncio
async def test_sync_years_overlapping_requests():
    """겹치는 범위 요청 시 중복 방지 테스트"""
    guard = HolidaySyncGuard()
    mock_sync = AsyncMock()
    
    # 두 범위가 겹침: 2024-2025, 2025-2026
    task1 = asyncio.create_task(guard.sync_years(2024, 2025, mock_sync))
    await asyncio.sleep(0.01)  # 첫 번째가 시작되도록
    task2 = asyncio.create_task(guard.sync_years(2025, 2026, mock_sync))
    
    await asyncio.gather(task1, task2)
    
    # 2024: 1번, 2025: 1번 (중복 방지), 2026: 1번
    assert mock_sync.call_count == 3
    called_years = [call[0][0] for call in mock_sync.call_args_list]
    assert set(called_years) == {2024, 2025, 2026}


@pytest.mark.asyncio
async def test_sync_year_exception_handling():
    """동기화 실패 시에도 이벤트가 제대로 set되는지 테스트"""
    guard = HolidaySyncGuard()
    
    async def failing_sync(year: int):
        raise ValueError(f"Sync failed for {year}")
    
    # 예외가 발생해도 완료 이벤트는 set되어야 함
    with pytest.raises(ValueError):
        await guard.sync_year(2024, failing_sync)
    
    # 이후 다시 호출하면 새로 실행되어야 함 (이전 이벤트 정리됨)
    mock_sync = AsyncMock()
    await guard.sync_year(2024, mock_sync)
    assert mock_sync.call_count == 1


@pytest.mark.asyncio
async def test_is_syncing():
    """is_syncing 메서드 테스트"""
    guard = HolidaySyncGuard()
    mock_sync = AsyncMock()
    
    # 동기화 시작 (비동기)
    task = asyncio.create_task(guard.sync_year(2024, mock_sync))
    await asyncio.sleep(0.01)  # 시작되도록 대기
    
    # 진행 중이어야 함
    assert guard.is_syncing(2024) is True
    assert guard.is_syncing(2025) is False
    
    # 완료 대기
    await task
    
    # 완료 후에는 False
    assert guard.is_syncing(2024) is False

