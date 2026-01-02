"""
Timezone Service 테스트

타임존 파싱 로직 검증:
- UTC 타임존 파싱
- UTC offset 형식 파싱 (+09:00, -05:00)
- 타임존 이름 파싱 (Asia/Seoul 등)
- 잘못된 타임존 형식 에러 처리
"""
from datetime import timezone, timedelta

import pytest

from app.domain.dateutil.exceptions import InvalidTimezoneError
from app.domain.dateutil.service import parse_timezone


class TestParseTimezone:
    """parse_timezone 함수 테스트"""

    def test_parse_utc(self):
        """UTC 타임존 파싱"""
        assert parse_timezone("UTC") == timezone.utc
        assert parse_timezone("utc") == timezone.utc
        assert parse_timezone("UtC") == timezone.utc

    def test_parse_none(self):
        """None 처리"""
        assert parse_timezone(None) == timezone.utc

    def test_parse_utc_offset_positive(self):
        """양수 UTC offset 파싱"""
        tz = parse_timezone("+09:00")

        assert tz == timezone(timedelta(hours=9))
        assert tz.utcoffset(None) == timedelta(hours=9)

    def test_parse_utc_offset_negative(self):
        """음수 UTC offset 파싱"""
        tz = parse_timezone("-05:00")

        assert tz == timezone(timedelta(hours=-5))
        assert tz.utcoffset(None) == timedelta(hours=-5)

    def test_parse_utc_offset_with_minutes(self):
        """분 단위가 포함된 UTC offset 파싱"""
        tz = parse_timezone("+05:30")  # 인도 표준시

        assert tz == timezone(timedelta(hours=5, minutes=30))
        assert tz.utcoffset(None) == timedelta(hours=5, minutes=30)

    def test_parse_utc_offset_without_minutes(self):
        """분 단위가 없는 UTC offset 파싱"""
        tz = parse_timezone("+09")

        assert tz == timezone(timedelta(hours=9))

    def test_parse_utc_offset_with_seconds(self):
        """초 단위가 포함된 UTC offset 파싱"""
        tz = parse_timezone("+09:00:30")

        assert tz == timezone(timedelta(hours=9, seconds=30))
        assert tz.utcoffset(None) == timedelta(hours=9, seconds=30)

    def test_parse_utc_offset_with_minutes_and_seconds(self):
        """분과 초 단위가 모두 포함된 UTC offset 파싱"""
        tz = parse_timezone("+05:30:45")

        assert tz == timezone(timedelta(hours=5, minutes=30, seconds=45))
        assert tz.utcoffset(None) == timedelta(hours=5, minutes=30, seconds=45)

    def test_parse_timezone_name_zoneinfo(self):
        """타임존 이름 파싱 (zoneinfo 사용)"""
        from zoneinfo import ZoneInfo
        try:
            tz = parse_timezone("Asia/Seoul")

            # ZoneInfo 객체인지 확인
            assert isinstance(tz, ZoneInfo)
            assert str(tz) == "Asia/Seoul"
        except InvalidTimezoneError:
            # tzdata 패키지가 없거나 타임존을 찾을 수 없는 경우
            pytest.skip("tzdata package not installed or timezone not found")

    def test_parse_invalid_offset_format(self):
        """잘못된 offset 형식 에러"""
        with pytest.raises(InvalidTimezoneError):
            parse_timezone("+")  # 형식이 완전하지 않음

        with pytest.raises(InvalidTimezoneError):
            parse_timezone("+abc")  # 숫자가 아님

        with pytest.raises(InvalidTimezoneError):
            parse_timezone("+:")  # 잘못된 형식

        with pytest.raises(InvalidTimezoneError):
            parse_timezone("+09:abc")  # 분이 숫자가 아님

    def test_parse_invalid_timezone_name(self):
        """잘못된 타임존 이름 에러"""
        with pytest.raises(InvalidTimezoneError) as exc_info:
            parse_timezone("Invalid/Timezone")

        assert "Invalid timezone name" in str(exc_info.value.detail)

    def test_parse_timezone_edge_cases(self):
        """엣지 케이스 테스트"""
        # 빈 문자열은 타임존 이름으로 처리되어 에러 발생 가능
        # (실제 구현에 따라 다를 수 있음)
        pass  # 빈 문자열 처리는 실제 동작에 따라 테스트 작성
