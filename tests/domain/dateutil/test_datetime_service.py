"""
Datetime Service 테스트

UTC 변환 및 datetime 처리 로직 검증:
- timezone이 있는 datetime을 UTC naive로 변환
- timezone이 없는 datetime은 그대로 반환
- 다른 timezone (예: KST)을 UTC로 변환
- None 처리
- RRULE 포맷팅
- datetime 비교 및 범위 계산
"""
from datetime import datetime, timezone, timedelta

from app.domain.dateutil.service import (
    ensure_utc_naive,
    to_utc_naive,
    format_datetime_for_rrule,
    is_datetime_within_tolerance,
    get_datetime_range,
)


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

        # UTC로 변환하면 10:00이 되어야 함
        assert result.tzinfo is None
        assert result == datetime(2024, 1, 1, 10, 0, 0)

    def test_naive_datetime_unchanged(self):
        """naive datetime은 그대로 반환"""
        dt = datetime(2024, 1, 1, 10, 0, 0)
        result = ensure_utc_naive(dt)

        assert result == dt
        assert result.tzinfo is None

    def test_none_handling(self):
        """None 처리"""
        assert ensure_utc_naive(None) is None

    def test_est_timezone_to_utc_naive(self):
        """EST timezone이 있는 datetime을 UTC naive로 변환"""
        # EST는 UTC-5
        est = timezone(timedelta(hours=-5))
        dt = datetime(2024, 1, 1, 5, 0, 0, tzinfo=est)  # EST 05:00

        result = ensure_utc_naive(dt)

        # EST 05:00 = UTC 10:00
        assert result.tzinfo is None
        assert result == datetime(2024, 1, 1, 10, 0, 0)

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
        """naive datetime은 그대로 반환"""
        dt = datetime(2024, 1, 1, 10, 0, 0)
        result = to_utc_naive(dt)

        assert result == dt
        assert result.tzinfo is None

    def test_none_handling(self):
        """None 처리"""
        assert to_utc_naive(None) is None


class TestFormatDatetimeForRrule:
    """format_datetime_for_rrule 함수 테스트"""

    def test_format_datetime(self):
        """datetime을 RRULE UNTIL 형식으로 변환"""
        dt = datetime(2024, 1, 29, 23, 59, 59)
        result = format_datetime_for_rrule(dt)

        assert result == "20240129T235959"

    def test_format_datetime_with_different_values(self):
        """다양한 datetime 값 포맷팅"""
        test_cases = [
            (datetime(2024, 1, 1, 0, 0, 0), "20240101T000000"),
            (datetime(2024, 12, 31, 23, 59, 59), "20241231T235959"),
            (datetime(2024, 6, 15, 12, 30, 45), "20240615T123045"),
        ]

        for dt, expected in test_cases:
            assert format_datetime_for_rrule(dt) == expected


class TestIsDatetimeWithinTolerance:
    """is_datetime_within_tolerance 함수 테스트"""

    def test_datetime_within_tolerance(self):
        """허용 오차 내의 datetime 비교"""
        dt1 = datetime(2024, 1, 1, 10, 0, 0)
        dt2 = datetime(2024, 1, 1, 10, 0, 30)  # 30초 차이

        assert is_datetime_within_tolerance(dt1, dt2, tolerance_seconds=60) is True

    def test_datetime_outside_tolerance(self):
        """허용 오차 밖의 datetime 비교"""
        dt1 = datetime(2024, 1, 1, 10, 0, 0)
        dt2 = datetime(2024, 1, 1, 10, 2, 0)  # 2분 차이

        assert is_datetime_within_tolerance(dt1, dt2, tolerance_seconds=60) is False

    def test_exact_match(self):
        """정확히 일치하는 datetime"""
        dt = datetime(2024, 1, 1, 10, 0, 0)

        assert is_datetime_within_tolerance(dt, dt, tolerance_seconds=60) is True

    def test_default_tolerance(self):
        """기본 허용 오차 사용"""
        dt1 = datetime(2024, 1, 1, 10, 0, 0)
        dt2 = datetime(2024, 1, 1, 10, 0, 59)  # 59초 차이 (기본값 60초 이내)

        assert is_datetime_within_tolerance(dt1, dt2) is True

        dt3 = datetime(2024, 1, 1, 10, 1, 1)  # 61초 차이

        assert is_datetime_within_tolerance(dt1, dt3) is False

    def test_negative_time_diff(self):
        """음수 시간 차이 처리 (절대값 사용)"""
        dt1 = datetime(2024, 1, 1, 10, 0, 30)
        dt2 = datetime(2024, 1, 1, 10, 0, 0)  # dt1이 더 늦음

        assert is_datetime_within_tolerance(dt1, dt2, tolerance_seconds=60) is True


class TestGetDatetimeRange:
    """get_datetime_range 함수 테스트"""

    def test_get_datetime_range_default_tolerance(self):
        """기본 허용 오차로 범위 계산"""
        dt = datetime(2024, 1, 1, 10, 0, 0)
        start_range, end_range = get_datetime_range(dt)

        expected_start = datetime(2024, 1, 1, 9, 59, 0)  # 60초 전
        expected_end = datetime(2024, 1, 1, 10, 1, 0)  # 60초 후

        assert start_range == expected_start
        assert end_range == expected_end

    def test_get_datetime_range_custom_tolerance(self):
        """커스텀 허용 오차로 범위 계산"""
        dt = datetime(2024, 1, 1, 10, 0, 0)
        start_range, end_range = get_datetime_range(dt, tolerance_seconds=120)

        expected_start = datetime(2024, 1, 1, 9, 58, 0)  # 120초 전
        expected_end = datetime(2024, 1, 1, 10, 2, 0)  # 120초 후

        assert start_range == expected_start
        assert end_range == expected_end

    def test_get_datetime_range_zero_tolerance(self):
        """0 초 허용 오차"""
        dt = datetime(2024, 1, 1, 10, 0, 0)
        start_range, end_range = get_datetime_range(dt, tolerance_seconds=0)

        assert start_range == dt
        assert end_range == dt

    def test_ensure_utc_naive_vs_to_utc_naive_difference(self):
        """ensure_utc_naive와 to_utc_naive의 차이점 확인"""
        from app.domain.dateutil.service import to_utc_naive

        # UTC timezone이 있는 경우
        utc_dt = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        result_ensure = ensure_utc_naive(utc_dt)
        result_to = to_utc_naive(utc_dt)

        # 둘 다 같은 결과를 반환해야 함
        assert result_ensure == result_to
        assert result_ensure == datetime(2024, 1, 1, 10, 0, 0)  # KST timezone이 있는 경우
        kst = timezone(timedelta(hours=9))
        kst_dt = datetime(2024, 1, 1, 19, 0, 0, tzinfo=kst)
        result_ensure = ensure_utc_naive(kst_dt)
        result_to = to_utc_naive(kst_dt)

        # 둘 다 같은 결과를 반환해야 함
        assert result_ensure == result_to
        assert result_ensure == datetime(2024, 1, 1, 10, 0, 0)

        def test_ensure_utc_naive_with_microseconds(self):
            """마이크로초가 포함된 datetime 처리"""

        dt = datetime(2024, 1, 1, 10, 0, 0, 123456, tzinfo=timezone.utc)
        result = ensure_utc_naive(dt)

        assert result == datetime(2024, 1, 1, 10, 0, 0, 123456)
        assert result.microsecond == 123456

    def test_get_datetime_range_with_microseconds(self):
        """마이크로초가 포함된 datetime 범위 계산"""
        dt = datetime(2024, 1, 1, 10, 0, 0, 500000)
        start_range, end_range = get_datetime_range(dt, tolerance_seconds=30)

        expected_start = datetime(2024, 1, 1, 9, 59, 30, 500000)
        expected_end = datetime(2024, 1, 1, 10, 0, 30, 500000)

        assert start_range == expected_start
        assert end_range == expected_end

    def test_is_datetime_within_tolerance_with_microseconds(self):
        """마이크로초 차이가 있는 datetime 비교"""
        dt1 = datetime(2024, 1, 1, 10, 0, 0, 0)
        dt2 = datetime(2024, 1, 1, 10, 0, 0, 500000)  # 0.5초 차이

        # 1초 허용 오차 내에 있어야 함
        assert is_datetime_within_tolerance(dt1, dt2, tolerance_seconds=1) is True

        # 0.1초 허용 오차 밖에 있어야 함
        assert is_datetime_within_tolerance(dt1, dt2, tolerance_seconds=0) is False
