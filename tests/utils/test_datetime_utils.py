"""
Datetime Utils 테스트

UTC 변환 로직 검증:
- timezone이 있는 datetime을 UTC naive로 변환
- timezone이 없는 datetime은 그대로 반환
- 다른 timezone (예: KST)을 UTC로 변환
- None 처리
"""
import pytest
from datetime import datetime, timezone, timedelta
from app.utils.datetime_utils import ensure_utc_naive, to_utc_naive


class TestEnsureUtcNaive:
    """ensure_utc_naive 함수 테스트"""

    def test_utc_timezone_to_naive(self):
        """UTC timezone이 있는 datetime을 naive로 변환"""
        dt = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        result = ensure_utc_naive(dt)
        
        assert result.tzinfo is None
        assert result == datetime(2024, 1, 1, 10, 0, 0)

    def test_kst_timezone_to_utc_naive(self):
        """KST timezone이 있는 datetime을 UTC naive로 변환"""
        # KST는 UTC+9
        kst = timezone(timedelta(hours=9))
        dt = datetime(2024, 1, 1, 19, 0, 0, tzinfo=kst)  # KST 19:00
        
        result = ensure_utc_naive(dt)
        
        # KST 19:00 = UTC 10:00
        assert result.tzinfo is None
        assert result == datetime(2024, 1, 1, 10, 0, 0)

    def test_est_timezone_to_utc_naive(self):
        """EST timezone이 있는 datetime을 UTC naive로 변환"""
        # EST는 UTC-5
        est = timezone(timedelta(hours=-5))
        dt = datetime(2024, 1, 1, 5, 0, 0, tzinfo=est)  # EST 05:00
        
        result = ensure_utc_naive(dt)
        
        # EST 05:00 = UTC 10:00
        assert result.tzinfo is None
        assert result == datetime(2024, 1, 1, 10, 0, 0)

    def test_naive_datetime_unchanged(self):
        """timezone이 없는 datetime은 그대로 반환"""
        dt = datetime(2024, 1, 1, 10, 0, 0)
        result = ensure_utc_naive(dt)
        
        assert result.tzinfo is None
        assert result == dt

    def test_none_handling(self):
        """None 입력 시 None 반환"""
        result = ensure_utc_naive(None)
        assert result is None

    def test_preserves_time_value(self):
        """시간 값이 올바르게 보존되는지 확인"""
        # 다양한 timezone에서 같은 UTC 시간으로 변환되는지 확인
        utc_dt = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        kst = timezone(timedelta(hours=9))
        kst_dt = datetime(2024, 1, 1, 19, 0, 0, tzinfo=kst)
        
        utc_result = ensure_utc_naive(utc_dt)
        kst_result = ensure_utc_naive(kst_dt)
        
        # 둘 다 같은 UTC naive datetime이 되어야 함
        assert utc_result == kst_result
        assert utc_result == datetime(2024, 1, 1, 10, 0, 0)


class TestToUtcNaive:
    """to_utc_naive 함수 테스트"""

    def test_utc_timezone_to_naive(self):
        """UTC timezone이 있는 datetime을 naive로 변환"""
        dt = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        result = to_utc_naive(dt)
        
        assert result.tzinfo is None
        assert result == datetime(2024, 1, 1, 10, 0, 0)

    def test_kst_timezone_to_utc_naive(self):
        """KST timezone이 있는 datetime을 UTC naive로 변환"""
        kst = timezone(timedelta(hours=9))
        dt = datetime(2024, 1, 1, 19, 0, 0, tzinfo=kst)
        
        result = to_utc_naive(dt)
        
        assert result.tzinfo is None
        assert result == datetime(2024, 1, 1, 10, 0, 0)

    def test_naive_datetime_unchanged(self):
        """timezone이 없는 datetime은 그대로 반환"""
        dt = datetime(2024, 1, 1, 10, 0, 0)
        result = to_utc_naive(dt)
        
        assert result.tzinfo is None
        assert result == dt

    def test_none_handling(self):
        """None 입력 시 None 반환"""
        result = to_utc_naive(None)
        assert result is None

