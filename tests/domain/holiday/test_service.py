"""
Holiday Service 테스트

HolidayService와 HolidayReadService 테스트
"""
import pytest
from datetime import datetime
from sqlmodel import Session

from app.domain.holiday.service import HolidayService, HolidayReadService
from app.domain.holiday.schema.dto import HolidayItem
from app.domain.holiday.model import HolidayModel


def test_holiday_read_service_get_holidays_single_year(test_session):
    """HolidayReadService 단일 연도 조회 테스트"""
    # 테스트 데이터 준비
    holiday = HolidayModel(
        date=datetime(2024, 1, 1),
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
    holidays_2024 = [
        HolidayModel(
            date=datetime(2024, 1, 1),
            dateName="신정",
            isHoliday=True,
            dateKind="국경일",
        ),
        HolidayModel(
            date=datetime(2024, 3, 1),
            dateName="삼일절",
            isHoliday=True,
            dateKind="국경일",
        ),
    ]
    # 2025년 데이터
    holidays_2025 = [
        HolidayModel(
            date=datetime(2025, 1, 1),
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
    holiday = HolidayModel(
        date=datetime(2024, 1, 1),
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
