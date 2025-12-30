"""
Timezone Conversion 테스트

타임존 변환 로직 검증:
- UTC naive datetime을 지정된 타임존의 aware datetime으로 변환
- 문자열 타임존 파싱 및 변환
- None 처리
"""
import pytest
from datetime import datetime, timezone, timedelta

from app.domain.dateutil.service import convert_utc_naive_to_timezone
from app.domain.dateutil.exceptions import InvalidTimezoneError


class TestConvertUtcNaiveToTimezone:
    """convert_utc_naive_to_timezone 함수 테스트"""

    def test_convert_to_utc_timezone_object(self):
        """timezone 객체를 사용한 UTC 변환"""
        dt = datetime(2024, 1, 1, 10, 0, 0)  # UTC naive
        result = convert_utc_naive_to_timezone(dt, timezone.utc)
        
        assert result.tzinfo == timezone.utc
        assert result == datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

    def test_convert_to_kst_timezone_object(self):
        """timezone 객체를 사용한 KST 변환"""
        dt = datetime(2024, 1, 1, 10, 0, 0)  # UTC naive (UTC 10:00)
        kst = timezone(timedelta(hours=9))
        result = convert_utc_naive_to_timezone(dt, kst)
        
        assert result.tzinfo == kst
        # UTC 10:00은 KST 19:00
        assert result == datetime(2024, 1, 1, 19, 0, 0, tzinfo=kst)

    def test_convert_to_utc_offset_string(self):
        """UTC offset 문자열을 사용한 변환"""
        dt = datetime(2024, 1, 1, 10, 0, 0)  # UTC naive
        result = convert_utc_naive_to_timezone(dt, "+09:00")
        
        expected_tz = timezone(timedelta(hours=9))
        assert result.tzinfo == expected_tz
        assert result == datetime(2024, 1, 1, 19, 0, 0, tzinfo=expected_tz)

    def test_convert_to_timezone_name_string(self):
        """타임존 이름 문자열을 사용한 변환"""
        try:
            from zoneinfo import ZoneInfo
            dt = datetime(2024, 1, 1, 10, 0, 0)  # UTC naive
            try:
                result = convert_utc_naive_to_timezone(dt, "Asia/Seoul")
                
                assert result.tzinfo is not None
                # Asia/Seoul은 UTC+9이므로 UTC 10:00은 KST 19:00
                assert result.hour == 19
            except InvalidTimezoneError:
                # tzdata 패키지가 없거나 타임존을 찾을 수 없는 경우
                pytest.skip("tzdata package not installed or timezone not found")
        except ImportError:
            pytest.skip("zoneinfo not available")

    def test_convert_none_timezone(self):
        """타임존이 None인 경우"""
        dt = datetime(2024, 1, 1, 10, 0, 0)
        result = convert_utc_naive_to_timezone(dt, None)
        
        assert result == dt  # 그대로 반환

    def test_convert_none_datetime(self):
        """datetime이 None인 경우"""
        assert convert_utc_naive_to_timezone(None, timezone.utc) is None
        assert convert_utc_naive_to_timezone(None, "+09:00") is None

    def test_convert_invalid_timezone_string(self):
        """잘못된 타임존 문자열 에러"""
        dt = datetime(2024, 1, 1, 10, 0, 0)
        
        with pytest.raises(InvalidTimezoneError):
            convert_utc_naive_to_timezone(dt, "Invalid/Timezone")

    def test_convert_various_timezones(self):
        """다양한 타임존으로 변환"""
        dt = datetime(2024, 1, 1, 12, 0, 0)  # UTC noon
        
        test_cases = [
            ("+00:00", 12),  # UTC
            ("+09:00", 21),  # KST (UTC+9)
            ("-05:00", 7),   # EST (UTC-5)
            ("+05:30", 17),  # IST (UTC+5:30)
        ]
        
        for tz_str, expected_hour in test_cases:
            result = convert_utc_naive_to_timezone(dt, tz_str)
            assert result.hour == expected_hour
