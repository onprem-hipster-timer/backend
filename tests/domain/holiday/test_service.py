"""
Holiday Service 테스트

HolidayService와 HolidayReadService 테스트
"""
import pytest
from datetime import datetime
from sqlmodel import Session
from zoneinfo import ZoneInfo
from datetime import timezone as tz

from app.domain.holiday.service import HolidayService, HolidayReadService
from app.domain.holiday.schema.dto import HolidayItem
from app.domain.holiday.model import HolidayModel


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
