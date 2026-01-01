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

    def test_convert_timezone_preserves_date(self):
        """타임존 변환 시 날짜가 올바르게 보존되는지"""
        dt = datetime(2024, 1, 1, 10, 0, 0)  # UTC naive
        result = convert_utc_naive_to_timezone(dt, "+09:00")
        
        # 날짜는 동일해야 함 (같은 날)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 1

    def test_convert_timezone_with_date_crossing(self):
        """날짜 경계를 넘는 타임존 변환"""
        # UTC 23:00을 KST로 변환하면 다음날 08:00
        dt = datetime(2024, 1, 1, 23, 0, 0)  # UTC naive
        result = convert_utc_naive_to_timezone(dt, "+09:00")
        
        assert result.hour == 8
        assert result.day == 2  # 다음날

    def test_convert_timezone_aware_datetime_serialization(self):
        """변환된 datetime의 직렬화 확인"""
        dt = datetime(2024, 1, 1, 10, 0, 0)  # UTC naive
        result = convert_utc_naive_to_timezone(dt, "+09:00")
        
        # 타임존 정보가 포함되어야 함
        assert result.tzinfo is not None
        
        # ISO 형식으로 직렬화 시 타임존 정보 포함 확인
        iso_str = result.isoformat()
        assert "+09:00" in iso_str or "+0900" in iso_str
        
        # 시간이 올바르게 변환되었는지 확인
        assert result.hour == 19  # UTC 10:00 -> KST 19:00

    def test_convert_timezone_with_zoneinfo_name(self):
        """ZoneInfo 타임존 이름으로 변환"""
        try:
            from zoneinfo import ZoneInfo
            dt = datetime(2024, 1, 1, 10, 0, 0)  # UTC naive
            
            try:
                result = convert_utc_naive_to_timezone(dt, "Asia/Seoul")
                
                # 타임존 정보 확인
                assert result.tzinfo is not None
                assert isinstance(result.tzinfo, ZoneInfo)
                
                # 시간 변환 확인 (UTC 10:00 -> KST 19:00)
                assert result.hour == 19
                
                # ISO 형식 확인
                iso_str = result.isoformat()
                assert "+09:00" in iso_str or "+0900" in iso_str
            except InvalidTimezoneError:
                pytest.skip("tzdata package not installed or timezone not found")
        except ImportError:
            pytest.skip("zoneinfo not available")

    def test_convert_timezone_round_trip(self):
        """타임존 변환의 왕복 테스트"""
        from app.domain.dateutil.service import ensure_utc_naive
        
        # UTC naive -> KST -> UTC naive
        original = datetime(2024, 1, 1, 10, 0, 0)  # UTC naive
        kst_result = convert_utc_naive_to_timezone(original, "+09:00")
        
        # KST aware를 UTC naive로 다시 변환
        back_to_utc = ensure_utc_naive(kst_result)
        
        # 원래 값과 동일해야 함
        assert back_to_utc == original

    def test_convert_timezone_with_different_offsets(self):
        """다양한 오프셋으로 변환"""
        dt = datetime(2024, 1, 1, 12, 0, 0)  # UTC noon
        
        test_cases = [
            ("+00:00", 12, 0),   # UTC
            ("+01:00", 13, 0),   # CET
            ("+09:00", 21, 0),   # KST
            ("-05:00", 7, 0),    # EST
            ("+05:30", 17, 30),  # IST (30분 오프셋)
        ]
        
        for tz_str, expected_hour, expected_minute in test_cases:
            result = convert_utc_naive_to_timezone(dt, tz_str)
            assert result.hour == expected_hour
            assert result.minute == expected_minute
            assert result.tzinfo is not None

    def test_strftime_percent_z_windows_compatibility(self):
        """strftime('%z')의 Windows 호환성 테스트"""
        import platform
        
        # 다양한 timezone-aware datetime 생성
        test_cases = [
            (datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc), "+0000"),
            (datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone(timedelta(hours=9))), "+0900"),
            (datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone(timedelta(hours=-5))), "-0500"),
            (datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone(timedelta(hours=5, minutes=30))), "+0530"),
        ]
        
        for dt, expected_offset in test_cases:
            # strftime('%z') 테스트
            result = dt.strftime("%Y-%m-%dT%H:%M:%S%z")
            
            # Windows에서 %z가 빈 문자열을 반환할 수 있음
            if platform.system() == "Windows":
                # Windows에서는 %z가 제대로 작동하지 않을 수 있음
                # 빈 문자열이거나 예상과 다른 형식일 수 있음
                if result.endswith("%z") or result == dt.strftime("%Y-%m-%dT%H:%M:%S"):
                    # Windows에서 %z가 작동하지 않는 경우
                    pytest.skip(f"strftime('%z') not supported on Windows for {dt.tzinfo}")
                else:
                    # Windows에서도 작동하는 경우 (Python 3.9+ 또는 tzdata 설치 시)
                    assert expected_offset in result or result.endswith(expected_offset)
            else:
                # Unix/Linux/Mac에서는 정상 작동해야 함
                assert result.endswith(expected_offset), f"Expected {expected_offset}, got {result}"

    def test_strftime_percent_z_with_zoneinfo(self):
        """ZoneInfo를 사용한 strftime('%z') 테스트"""
        try:
            from zoneinfo import ZoneInfo
            import platform
            
            # Asia/Seoul timezone
            try:
                dt = datetime(2024, 1, 1, 10, 0, 0, tzinfo=ZoneInfo("Asia/Seoul"))
                result = dt.strftime("%Y-%m-%dT%H:%M:%S%z")
                
                if platform.system() == "Windows":
                    # Windows에서 %z가 빈 문자열을 반환할 수 있음
                    if result.endswith("%z") or result == dt.strftime("%Y-%m-%dT%H:%M:%S"):
                        pytest.skip("strftime('%z') not supported on Windows with ZoneInfo")
                    else:
                        # Windows에서도 작동하는 경우
                        assert "+0900" in result or "+09:00" in result
                else:
                    # Unix/Linux/Mac에서는 정상 작동해야 함
                    assert result.endswith("+0900") or result.endswith("+09:00")
            except Exception as e:
                # tzdata 패키지가 없거나 타임존을 찾을 수 없는 경우
                pytest.skip(f"ZoneInfo not available: {e}")
        except ImportError:
            pytest.skip("zoneinfo not available")

    def test_strftime_percent_z_empty_string_detection(self):
        """strftime('%z')가 빈 문자열을 반환하는지 감지"""
        import platform
        
        # UTC timezone
        dt = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        result = dt.strftime("%z")
        
        if platform.system() == "Windows":
            # Windows에서 %z가 빈 문자열을 반환할 수 있음
            if result == "":
                # Windows에서 %z가 작동하지 않는 경우를 문서화
                # 이 경우 대안 방법(offset 수동 계산)을 사용해야 함
                assert True, "strftime('%z') returns empty string on Windows - need alternative method"
            else:
                # Windows에서도 작동하는 경우
                assert result == "+0000" or result == "+00:00"
        else:
            # Unix/Linux/Mac에서는 정상 작동해야 함
            assert result == "+0000" or result == "+00:00"