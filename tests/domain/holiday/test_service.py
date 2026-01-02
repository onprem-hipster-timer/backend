"""
Holiday Service 테스트

HolidayService와 HolidayReadService 테스트
"""
import pytest
from datetime import datetime
from zoneinfo import ZoneInfo
from datetime import timezone as tz
from unittest.mock import AsyncMock, MagicMock, patch

from app.domain.holiday.service import HolidayService, HolidayReadService
from app.domain.holiday.schema.dto import HolidayItem
from app.domain.holiday.model import HolidayModel, HolidayHashModel


def _create_holiday_date_range(locdate: str) -> tuple[datetime, datetime]:
    """한국 표준시 기준 24시간 범위 생성"""
    year = int(locdate[0:4])
    month = int(locdate[4:6])
    day = int(locdate[6:8])
    
    kst = ZoneInfo("Asia/Seoul")
    kst_start = datetime(year, month, day, 0, 0, 0, 0, tzinfo=kst)
    kst_end = datetime(year, month, day, 23, 59, 59, 999999, tzinfo=kst)
    
    utc_start = kst_start.astimezone(tz.utc).replace(tzinfo=None)
    utc_end = kst_end.astimezone(tz.utc).replace(tzinfo=None)
    
    return (utc_start, utc_end)


def test_holiday_read_service_get_holidays_single_year(test_session):
    """HolidayReadService 단일 연도 조회 테스트"""
    # 테스트 데이터 준비
    start_date, end_date = _create_holiday_date_range("20240101")
    holiday = HolidayModel(
        start_date=start_date,
        end_date=end_date,
        dateName="신정",
        isHoliday=True,
        dateKind="국경일",
    )
    test_session.add(holiday)
    test_session.flush()
    
    service = HolidayReadService(test_session)
    holidays = service.get_holidays(2024)
    
    assert len(holidays) == 1
    assert holidays[0].dateName == "신정"
    assert holidays[0].locdate == "20240101"
    assert holidays[0].isHoliday is True


def test_holiday_read_service_get_holidays_range(test_session):
    """HolidayReadService 범위 조회 테스트"""
    # 2024년 데이터
    start1, end1 = _create_holiday_date_range("20240101")
    start2, end2 = _create_holiday_date_range("20240301")
    holidays_2024 = [
        HolidayModel(
            start_date=start1,
            end_date=end1,
            dateName="신정",
            isHoliday=True,
            dateKind="국경일",
        ),
        HolidayModel(
            start_date=start2,
            end_date=end2,
            dateName="삼일절",
            isHoliday=True,
            dateKind="국경일",
        ),
    ]
    # 2025년 데이터
    start3, end3 = _create_holiday_date_range("20250101")
    holidays_2025 = [
        HolidayModel(
            start_date=start3,
            end_date=end3,
            dateName="신정",
            isHoliday=True,
            dateKind="국경일",
        ),
    ]
    
    for h in holidays_2024 + holidays_2025:
        test_session.add(h)
    test_session.flush()
    
    service = HolidayReadService(test_session)
    holidays = service.get_holidays(2024, 2025)
    
    assert len(holidays) == 3
    years = {datetime.strptime(h.locdate, "%Y%m%d").year for h in holidays}
    assert years == {2024, 2025}


def test_holiday_read_service_get_holidays_empty(test_session):
    """HolidayReadService 빈 결과 테스트"""
    service = HolidayReadService(test_session)
    holidays = service.get_holidays(2024)
    
    assert len(holidays) == 0
    assert holidays == []


def test_holiday_read_service_get_holidays_default_end_year(test_session):
    """HolidayReadService end_year 미지정 시 start_year로 처리 테스트"""
    start_date, end_date = _create_holiday_date_range("20240101")
    holiday = HolidayModel(
        start_date=start_date,
        end_date=end_date,
        dateName="신정",
        isHoliday=True,
        dateKind="국경일",
    )
    test_session.add(holiday)
    test_session.flush()
    
    service = HolidayReadService(test_session)
    holidays = service.get_holidays(2024)  # end_year 미지정
    
    assert len(holidays) == 1


def test_holiday_read_service_get_holidays_with_kst_year_boundary(test_session):
    """HolidayReadService 한국 시간 기준 연도 경계 테스트"""
    # 2023년 12월 31일과 2024년 1월 1일 데이터 (한국 시간 기준)
    # 한국 시간 2023-12-31 → UTC 2023-12-30 15:00
    start1, end1 = _create_holiday_date_range("20231231")
    # 한국 시간 2024-01-01 → UTC 2023-12-31 15:00
    start2, end2 = _create_holiday_date_range("20240101")
    
    holidays = [
        HolidayModel(
            start_date=start1,
            end_date=end1,
            dateName="연말",
            isHoliday=True,
            dateKind="국경일",
        ),
        HolidayModel(
            start_date=start2,
            end_date=end2,
            dateName="신정",
            isHoliday=True,
            dateKind="국경일",
        ),
    ]
    
    for h in holidays:
        test_session.add(h)
    test_session.flush()
    
    service = HolidayReadService(test_session)
    
    # 2023년 조회 (한국 시간 기준)
    holidays_2023 = service.get_holidays(2023)
    assert len(holidays_2023) == 1
    assert holidays_2023[0].dateName == "연말"
    assert holidays_2023[0].locdate == "20231231"
    
    # 2024년 조회 (한국 시간 기준)
    holidays_2024 = service.get_holidays(2024)
    assert len(holidays_2024) == 1
    assert holidays_2024[0].dateName == "신정"
    assert holidays_2024[0].locdate == "20240101"


def test_get_holiday_by_date_with_kst_datetime(test_session):
    """한국 시간 기준 datetime으로 공휴일 조회 테스트"""
    from app.crud import holiday as crud
    
    # 한국 시간 2024년 1월 1일 신정 데이터 저장
    start_date, end_date = _create_holiday_date_range("20240101")
    holiday = HolidayModel(
        start_date=start_date,
        end_date=end_date,
        dateName="신정",
        isHoliday=True,
        dateKind="국경일",
    )
    test_session.add(holiday)
    test_session.flush()
    
    # 한국 시간 기준 datetime으로 조회
    kst = ZoneInfo("Asia/Seoul")
    kst_date = datetime(2024, 1, 1, 12, 0, 0, tzinfo=kst)  # 한국 시간 2024-01-01 12:00
    
    result = crud.get_holiday_by_date_sync(test_session, kst_date)
    
    assert result is not None
    assert result.dateName == "신정"
    assert result.isHoliday is True


def test_get_holiday_by_date_with_kst_datetime_not_found(test_session):
    """한국 시간 기준 datetime으로 조회 시 없는 날짜 테스트"""
    from app.crud import holiday as crud
    
    # 한국 시간 2024년 1월 1일 신정 데이터 저장
    start_date, end_date = _create_holiday_date_range("20240101")
    holiday = HolidayModel(
        start_date=start_date,
        end_date=end_date,
        dateName="신정",
        isHoliday=True,
        dateKind="국경일",
    )
    test_session.add(holiday)
    test_session.flush()
    
    # 한국 시간 기준 다른 날짜로 조회
    kst = ZoneInfo("Asia/Seoul")
    kst_date = datetime(2024, 1, 2, 12, 0, 0, tzinfo=kst)  # 한국 시간 2024-01-02 12:00
    
    result = crud.get_holiday_by_date_sync(test_session, kst_date)
    
    assert result is None


def test_get_holiday_by_date_with_utc_datetime(test_session):
    """UTC datetime으로 공휴일 조회 테스트 (한국 시간 기준 날짜 확인)"""
    from app.crud import holiday as crud
    
    # 한국 시간 2024년 1월 1일 신정 데이터 저장
    # DB에는 UTC 2023-12-31 15:00 ~ 2024-01-01 14:59로 저장됨
    start_date, end_date = _create_holiday_date_range("20240101")
    holiday = HolidayModel(
        start_date=start_date,
        end_date=end_date,
        dateName="신정",
        isHoliday=True,
        dateKind="국경일",
    )
    test_session.add(holiday)
    test_session.flush()
    
    # UTC datetime으로 조회 (한국 시간 2024-01-01에 해당하는 UTC 시간)
    utc_date = datetime(2024, 1, 1, 0, 0, 0, tzinfo=tz.utc)  # UTC 2024-01-01 00:00 (한국 시간 2024-01-01 09:00)
    
    result = crud.get_holiday_by_date_sync(test_session, utc_date)
    
    # UTC 2024-01-01 00:00은 한국 시간 2024-01-01 09:00이므로 신정 범위에 포함됨
    assert result is not None
    assert result.dateName == "신정"


def test_holiday_service_generate_hash():
    """HolidayService.generate_hash 테스트"""
    holidays = [
        HolidayItem(
            locdate="20240101",
            seq=1,
            dateKind="01",
            dateName="신정",
            isHoliday=True,
        ),
        HolidayItem(
            locdate="20240301",
            seq=1,
            dateKind="01",
            dateName="삼일절",
            isHoliday=True,
        ),
    ]
    
    hash1 = HolidayService.generate_hash(holidays)
    hash2 = HolidayService.generate_hash(holidays)
    
    # 같은 입력은 같은 해시
    assert hash1 == hash2
    assert len(hash1) == 64  # SHA256 해시 길이


def test_holiday_service_generate_hash_order_independent():
    """HolidayService.generate_hash 순서 독립성 테스트"""
    holidays1 = [
        HolidayItem(
            locdate="20240101",
            seq=1,
            dateKind="01",
            dateName="신정",
            isHoliday=True,
        ),
        HolidayItem(
            locdate="20240301",
            seq=1,
            dateKind="01",
            dateName="삼일절",
            isHoliday=True,
        ),
    ]
    
    # 순서가 달라도 같은 해시 (정렬되어 있음)
    holidays2 = list(reversed(holidays1))
    hash1 = HolidayService.generate_hash(holidays1)
    hash2 = HolidayService.generate_hash(holidays2)
    
    assert hash1 == hash2


def test_holiday_service_generate_hash_different():
    """HolidayService.generate_hash 다른 입력은 다른 해시 테스트"""
    holidays1 = [
        HolidayItem(
            locdate="20240101",
            seq=1,
            dateKind="01",
            dateName="신정",
            isHoliday=True,
        ),
    ]
    holidays2 = [
        HolidayItem(
            locdate="20240101",
            seq=1,
            dateKind="01",
            dateName="신정",
            isHoliday=True,
        ),
        HolidayItem(
            locdate="20240301",
            seq=1,
            dateKind="01",
            dateName="삼일절",
            isHoliday=True,
        ),
    ]
    
    hash1 = HolidayService.generate_hash(holidays1)
    hash2 = HolidayService.generate_hash(holidays2)
    
    assert hash1 != hash2


def test_holiday_service_generate_hash_empty():
    """HolidayService.generate_hash 빈 리스트 테스트"""
    holidays = []
    hash_value = HolidayService.generate_hash(holidays)
    
    assert hash_value is not None
    assert len(hash_value) == 64  # SHA256 해시 길이


# ============ 동기화 관련 테스트 ============

def test_deduplicate_holidays():
    """중복 공휴일 제거 테스트"""
    holidays_by_type = {
        "national": [
            HolidayItem(
                locdate="20240101",
                seq=1,
                dateKind="01",
                dateName="신정",
                isHoliday=True,
            ),
            HolidayItem(
                locdate="20240301",
                seq=1,
                dateKind="01",
                dateName="삼일절",
                isHoliday=True,
            ),
        ],
        "rest": [
            HolidayItem(
                locdate="20240101",  # 중복 (national과 동일)
                seq=1,
                dateKind="02",
                dateName="신정",
                isHoliday=True,
            ),
        ],
        "anniversaries": [],
        "divisions_24": [],
    }
    
    deduplicated = HolidayService._deduplicate_holidays(holidays_by_type)
    
    # 중복 제거되어 2개만 남아야 함
    assert len(deduplicated) == 2
    locdates = {h.locdate for h in deduplicated}
    assert locdates == {"20240101", "20240301"}


def test_deduplicate_holidays_empty():
    """빈 공휴일 딕셔너리 중복 제거 테스트"""
    holidays_by_type = {
        "national": [],
        "rest": [],
        "anniversaries": [],
        "divisions_24": [],
    }
    
    deduplicated = HolidayService._deduplicate_holidays(holidays_by_type)
    
    assert len(deduplicated) == 0
    assert deduplicated == []


@pytest.mark.asyncio
async def test_should_update_with_hash_change(test_async_session):
    """해시 변경 시 업데이트 필요 확인 테스트"""
    from app.crud import holiday as crud
    
    # 기존 해시 저장
    old_hash = "old_hash_value"
    hash_model = HolidayHashModel(year=2024, hash_value=old_hash)
    test_async_session.add(hash_model)
    await test_async_session.flush()
    
    service = HolidayService(test_async_session)
    new_hash = "new_hash_value"
    
    should_update, retrieved_hash = await service._should_update(2024, new_hash, False)
    
    assert should_update is True
    assert retrieved_hash == old_hash


@pytest.mark.asyncio
async def test_should_update_with_same_hash(test_async_session):
    """해시 동일 시 업데이트 불필요 확인 테스트"""
    from app.crud import holiday as crud
    
    # 기존 해시 저장
    same_hash = "same_hash_value"
    hash_model = HolidayHashModel(year=2024, hash_value=same_hash)
    test_async_session.add(hash_model)
    await test_async_session.flush()
    
    service = HolidayService(test_async_session)
    
    should_update, retrieved_hash = await service._should_update(2024, same_hash, False)
    
    assert should_update is False
    assert retrieved_hash == same_hash


@pytest.mark.asyncio
async def test_should_update_with_force(test_async_session):
    """강제 업데이트 시 항상 True 반환 테스트"""
    from app.crud import holiday as crud
    
    # 기존 해시 저장
    old_hash = "old_hash_value"
    hash_model = HolidayHashModel(year=2024, hash_value=old_hash)
    test_async_session.add(hash_model)
    await test_async_session.flush()
    
    service = HolidayService(test_async_session)
    new_hash = "new_hash_value"
    
    # 해시가 같아도 force_update=True면 True 반환
    should_update, retrieved_hash = await service._should_update(2024, old_hash, True)
    
    assert should_update is True
    assert retrieved_hash == old_hash


@pytest.mark.asyncio
async def test_should_update_with_no_existing_hash(test_async_session):
    """기존 해시가 없을 때 업데이트 필요 확인 테스트"""
    service = HolidayService(test_async_session)
    new_hash = "new_hash_value"
    
    should_update, retrieved_hash = await service._should_update(2024, new_hash, False)
    
    assert should_update is True
    assert retrieved_hash is None


def test_filter_missing_years():
    """존재하지 않는 연도 필터링 테스트"""
    existing_years = {2022, 2024, 2026}
    start_year = 2022
    end_year = 2026
    
    # HolidayService 인스턴스 생성 (session은 Mock)
    mock_session = MagicMock()
    service = HolidayService(mock_session)
    
    missing_years, skipped_count = service._filter_missing_years(
        existing_years, start_year, end_year
    )
    
    # 2022, 2024, 2026은 존재하므로 제외
    # 2023, 2025만 missing_years에 포함되어야 함
    assert set(missing_years) == {2023, 2025}
    assert skipped_count == 3  # 2022, 2024, 2026


def test_filter_missing_years_all_missing():
    """모든 연도가 존재하지 않을 때 테스트"""
    existing_years = set()
    start_year = 2024
    end_year = 2026
    
    mock_session = MagicMock()
    service = HolidayService(mock_session)
    
    missing_years, skipped_count = service._filter_missing_years(
        existing_years, start_year, end_year
    )
    
    assert set(missing_years) == {2024, 2025, 2026}
    assert skipped_count == 0


def test_filter_missing_years_all_exist():
    """모든 연도가 이미 존재할 때 테스트"""
    existing_years = {2024, 2025, 2026}
    start_year = 2024
    end_year = 2026
    
    mock_session = MagicMock()
    service = HolidayService(mock_session)
    
    missing_years, skipped_count = service._filter_missing_years(
        existing_years, start_year, end_year
    )
    
    assert len(missing_years) == 0
    assert skipped_count == 3


@pytest.mark.asyncio
async def test_get_existing_years(test_async_session):
    """존재하는 연도 조회 테스트"""
    # 해시 모델 생성
    hash_models = [
        HolidayHashModel(year=2022, hash_value="hash1"),
        HolidayHashModel(year=2024, hash_value="hash2"),
        HolidayHashModel(year=2026, hash_value="hash3"),
    ]
    for model in hash_models:
        test_async_session.add(model)
    await test_async_session.flush()
    
    service = HolidayService(test_async_session)
    existing_years = await service.get_existing_years()
    
    assert existing_years == {2022, 2024, 2026}


@pytest.mark.asyncio
async def test_get_existing_years_empty(test_async_session):
    """존재하는 연도가 없을 때 테스트"""
    service = HolidayService(test_async_session)
    existing_years = await service.get_existing_years()
    
    assert existing_years == set()


@pytest.mark.asyncio
async def test_sync_holidays_for_year_single(test_async_session):
    """단일 연도 동기화 테스트 (Mock 사용)"""
    from app.crud import holiday as crud
    
    # Mock API 클라이언트 설정
    mock_holidays = [
        HolidayItem(
            locdate="20240101",
            seq=1,
            dateKind="01",
            dateName="신정",
            isHoliday=True,
        ),
    ]
    
    with patch.object(HolidayService, '_fetch_all_holidays_for_year', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = {
            "national": mock_holidays,
            "rest": [],
            "anniversaries": [],
            "divisions_24": [],
        }
        
        # save_holidays Mock
        with patch.object(crud, 'save_holidays', new_callable=AsyncMock) as mock_save:
            with patch.object(crud, 'get_holiday_hash', new_callable=AsyncMock) as mock_get_hash:
                mock_get_hash.return_value = None  # 기존 해시 없음
                
                service = HolidayService(test_async_session)
                await service.sync_holidays_for_year(2024)
                
                # save_holidays가 호출되었는지 확인
                mock_save.assert_called_once()
                call_args = mock_save.call_args
                assert call_args[0][1] == 2024  # year 파라미터
                assert len(call_args[0][2]) == 1  # deduplicated holidays


@pytest.mark.asyncio
async def test_sync_holidays_for_year_skip_when_hash_same(test_async_session):
    """해시가 같을 때 동기화 건너뛰기 테스트"""
    from app.crud import holiday as crud
    
    # 기존 해시 저장
    existing_hash = "existing_hash"
    hash_model = HolidayHashModel(year=2024, hash_value=existing_hash)
    test_async_session.add(hash_model)
    await test_async_session.flush()
    
    mock_holidays = [
        HolidayItem(
            locdate="20240101",
            seq=1,
            dateKind="01",
            dateName="신정",
            isHoliday=True,
        ),
    ]
    
    with patch.object(HolidayService, '_fetch_all_holidays_for_year', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = {
            "national": mock_holidays,
            "rest": [],
            "anniversaries": [],
            "divisions_24": [],
        }
        
        with patch.object(crud, 'save_holidays', new_callable=AsyncMock) as mock_save:
            # 해시가 같다고 가정 (generate_hash가 같은 해시 반환)
            # get_holiday_hash는 실제 DB 조회 사용 (이미 DB에 저장했으므로)
            with patch.object(HolidayService, 'generate_hash') as mock_hash:
                mock_hash.return_value = existing_hash
                
                service = HolidayService(test_async_session)
                await service.sync_holidays_for_year(2024)
                
                # save_holidays가 호출되지 않아야 함
                mock_save.assert_not_called()


@pytest.mark.asyncio
async def test_sync_holidays_for_year_range(test_async_session):
    """범위 동기화 테스트"""
    from app.crud import holiday as crud
    
    mock_holidays = [
        HolidayItem(
            locdate="20240101",
            seq=1,
            dateKind="01",
            dateName="신정",
            isHoliday=True,
        ),
    ]
    
    with patch.object(HolidayService, '_fetch_all_holidays_for_year', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = {
            "national": mock_holidays,
            "rest": [],
            "anniversaries": [],
            "divisions_24": [],
        }
        
        with patch.object(crud, 'save_holidays', new_callable=AsyncMock) as mock_save:
            with patch.object(crud, 'get_holiday_hash', new_callable=AsyncMock) as mock_get_hash:
                mock_get_hash.return_value = None
                
                service = HolidayService(test_async_session)
                await service.sync_holidays_for_year(2024, end_year=2026)
                
                # 2024, 2025, 2026 각각 한 번씩 호출되어야 함
                assert mock_fetch.call_count == 3
                assert mock_save.call_count == 3
                
                # 호출된 연도 확인
                called_years = [call[0][1] for call in mock_save.call_args_list]
                assert set(called_years) == {2024, 2025, 2026}


@pytest.mark.asyncio
async def test_initialize_historical_data(test_async_session):
    """초기 데이터 로드 테스트"""
    from app.crud import holiday as crud
    
    # 일부 연도는 이미 존재
    existing_hash = HolidayHashModel(year=2022, hash_value="hash1")
    test_async_session.add(existing_hash)
    await test_async_session.flush()
    
    mock_holidays = [
        HolidayItem(
            locdate="20240101",
            seq=1,
            dateKind="01",
            dateName="신정",
            isHoliday=True,
        ),
    ]
    
    with patch.object(HolidayService, '_fetch_all_holidays_for_year', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = {
            "national": mock_holidays,
            "rest": [],
            "anniversaries": [],
            "divisions_24": [],
        }
        
        with patch.object(crud, 'save_holidays', new_callable=AsyncMock) as mock_save:
            # get_holiday_hash는 실제 DB 조회 사용 (2022는 이미 저장했으므로)
            service = HolidayService(test_async_session)
            result = await service.initialize_historical_data(2022, 2024)
            
            # 2022는 이미 존재하므로 제외, 2023, 2024만 동기화
            assert result is True
            assert mock_save.call_count == 2
            called_years = [call[0][1] for call in mock_save.call_args_list]
            assert set(called_years) == {2023, 2024}


@pytest.mark.asyncio
async def test_initialize_historical_data_all_exist(test_async_session):
    """모든 연도가 이미 존재할 때 초기화 건너뛰기 테스트"""
    # 모든 연도 존재
    for year in range(2022, 2025):
        hash_model = HolidayHashModel(year=year, hash_value=f"hash{year}")
        test_async_session.add(hash_model)
    await test_async_session.flush()
    
    service = HolidayService(test_async_session)
    result = await service.initialize_historical_data(2022, 2024)
    
    # 모든 연도가 이미 존재하므로 False 반환
    assert result is False
