"""
Locdate Service 테스트

locdate 파싱 및 연도 범위 변환 로직 검증:
- locdate 문자열(YYYYMMDD)을 한국 표준시 기준 24시간 범위로 변환
- 한국 표준시 기준 연도 범위를 UTC로 변환
- 잘못된 형식 에러 처리
"""
import pytest
from datetime import datetime
from zoneinfo import ZoneInfo

from app.domain.dateutil.service import (
    parse_locdate_to_datetime_range,
    get_year_range_utc,
)


class TestParseLocdateToDatetimeRange:
    """parse_locdate_to_datetime_range 함수 테스트"""

    def test_parse_valid_locdate(self):
        """유효한 locdate 파싱"""
        start_date, end_date = parse_locdate_to_datetime_range("20240101")
        
        # 한국 시간 2024-01-01 00:00:00 -> UTC 2023-12-31 15:00:00
        expected_start = datetime(2023, 12, 31, 15, 0, 0)
        # 한국 시간 2024-01-01 23:59:59.999999 -> UTC 2024-01-01 14:59:59.999999
        expected_end = datetime(2024, 1, 1, 14, 59, 59, 999999)
        
        assert start_date == expected_start
        assert end_date == expected_end
        assert start_date.tzinfo is None  # UTC naive
        assert end_date.tzinfo is None  # UTC naive

    def test_parse_locdate_mid_year(self):
        """연중 날짜 파싱"""
        start_date, end_date = parse_locdate_to_datetime_range("20240615")
        
        # 한국 시간 2024-06-15 00:00:00 -> UTC 2024-06-14 15:00:00
        expected_start = datetime(2024, 6, 14, 15, 0, 0)
        # 한국 시간 2024-06-15 23:59:59.999999 -> UTC 2024-06-15 14:59:59.999999
        expected_end = datetime(2024, 6, 15, 14, 59, 59, 999999)
        
        assert start_date == expected_start
        assert end_date == expected_end

    def test_parse_locdate_year_end(self):
        """연말 날짜 파싱"""
        start_date, end_date = parse_locdate_to_datetime_range("20231231")
        
        # 한국 시간 2023-12-31 00:00:00 -> UTC 2023-12-30 15:00:00
        expected_start = datetime(2023, 12, 30, 15, 0, 0)
        # 한국 시간 2023-12-31 23:59:59.999999 -> UTC 2023-12-31 14:59:59.999999
        expected_end = datetime(2023, 12, 31, 14, 59, 59, 999999)
        
        assert start_date == expected_start
        assert end_date == expected_end

    def test_parse_locdate_leap_year(self):
        """윤년 날짜 파싱"""
        start_date, end_date = parse_locdate_to_datetime_range("20240229")
        
        # 한국 시간 2024-02-29 00:00:00 -> UTC 2024-02-28 15:00:00
        expected_start = datetime(2024, 2, 28, 15, 0, 0)
        # 한국 시간 2024-02-29 23:59:59.999999 -> UTC 2024-02-29 14:59:59.999999
        expected_end = datetime(2024, 2, 29, 14, 59, 59, 999999)
        
        assert start_date == expected_start
        assert end_date == expected_end

    def test_parse_locdate_invalid_length(self):
        """잘못된 길이의 locdate 에러"""
        with pytest.raises(ValueError, match="Invalid locdate format"):
            parse_locdate_to_datetime_range("202401")  # 6자리
        
        with pytest.raises(ValueError, match="Invalid locdate format"):
            parse_locdate_to_datetime_range("202401011")  # 9자리
        
        with pytest.raises(ValueError, match="Invalid locdate format"):
            parse_locdate_to_datetime_range("")  # 빈 문자열

    def test_parse_locdate_invalid_format(self):
        """잘못된 형식의 locdate 에러"""
        with pytest.raises(ValueError, match="Invalid locdate format"):
            parse_locdate_to_datetime_range("2024abcd")  # 숫자가 아님
        
        with pytest.raises(ValueError, match="Invalid locdate format"):
            parse_locdate_to_datetime_range("20241301")  # 잘못된 월
        
        with pytest.raises(ValueError, match="Invalid locdate format"):
            parse_locdate_to_datetime_range("20240230")  # 잘못된 일

    def test_parse_locdate_verifies_kst_to_utc_conversion(self):
        """KST -> UTC 변환 검증"""
        # 한국 시간 기준으로 여러 날짜 테스트
        test_cases = [
            ("20240101", datetime(2023, 12, 31, 15, 0, 0), datetime(2024, 1, 1, 14, 59, 59, 999999)),
            ("20240701", datetime(2024, 6, 30, 15, 0, 0), datetime(2024, 7, 1, 14, 59, 59, 999999)),
            ("20241231", datetime(2024, 12, 30, 15, 0, 0), datetime(2024, 12, 31, 14, 59, 59, 999999)),
        ]
        
        for locdate, expected_start, expected_end in test_cases:
            start_date, end_date = parse_locdate_to_datetime_range(locdate)
            assert start_date == expected_start, f"Failed for {locdate}: expected {expected_start}, got {start_date}"
            assert end_date == expected_end, f"Failed for {locdate}: expected {expected_end}, got {end_date}"

    def test_parse_locdate_timezone_naive(self):
        """반환된 datetime이 timezone naive인지 확인"""
        start_date, end_date = parse_locdate_to_datetime_range("20240101")
        
        assert start_date.tzinfo is None
        assert end_date.tzinfo is None

    def test_parse_locdate_full_day_range(self):
        """24시간 범위가 올바르게 생성되는지 확인"""
        start_date, end_date = parse_locdate_to_datetime_range("20240101")
        
        # 시작과 끝 사이의 차이가 약 24시간인지 확인
        time_diff = (end_date - start_date).total_seconds()
        # 24시간 = 86400초, 마이크로초 포함하면 약간 더
        assert 86399 <= time_diff <= 86401  # 약간의 오차 허용


class TestGetYearRangeUtc:
    """get_year_range_utc 함수 테스트"""

    def test_get_year_range_utc_single_year(self):
        """단일 연도 범위 변환"""
        start_date, end_date = get_year_range_utc(2024)
        
        # 한국 시간 2024-01-01 00:00:00 -> UTC 2023-12-31 15:00:00
        expected_start = datetime(2023, 12, 31, 15, 0, 0)
        # 한국 시간 2024-12-31 23:59:59.999999 -> UTC 2024-12-31 14:59:59.999999
        expected_end = datetime(2024, 12, 31, 14, 59, 59, 999999)
        
        assert start_date == expected_start
        assert end_date == expected_end
        assert start_date.tzinfo is None  # UTC naive
        assert end_date.tzinfo is None  # UTC naive

    def test_get_year_range_utc_year_boundary(self):
        """연도 경계 테스트"""
        # 2023년 범위
        start_2023, end_2023 = get_year_range_utc(2023)
        # 한국 시간 2023-01-01 00:00:00 -> UTC 2022-12-31 15:00:00
        assert start_2023 == datetime(2022, 12, 31, 15, 0, 0)
        # 한국 시간 2023-12-31 23:59:59.999999 -> UTC 2023-12-31 14:59:59.999999
        assert end_2023 == datetime(2023, 12, 31, 14, 59, 59, 999999)
        
        # 2024년 범위
        start_2024, end_2024 = get_year_range_utc(2024)
        # 한국 시간 2024-01-01 00:00:00 -> UTC 2023-12-31 15:00:00
        assert start_2024 == datetime(2023, 12, 31, 15, 0, 0)
        # 한국 시간 2024-12-31 23:59:59.999999 -> UTC 2024-12-31 14:59:59.999999
        assert end_2024 == datetime(2024, 12, 31, 14, 59, 59, 999999)
        
        # 2023년 끝과 2024년 시작이 겹치는지 확인 (UTC 기준)
        assert end_2023 < start_2024  # 겹치지 않아야 함

    def test_get_year_range_utc_leap_year(self):
        """윤년 범위 테스트"""
        start_date, end_date = get_year_range_utc(2024)  # 2024는 윤년
        
        # 한국 시간 2024-01-01 00:00:00 -> UTC 2023-12-31 15:00:00
        assert start_date == datetime(2023, 12, 31, 15, 0, 0)
        # 한국 시간 2024-12-31 23:59:59.999999 -> UTC 2024-12-31 14:59:59.999999
        assert end_date == datetime(2024, 12, 31, 14, 59, 59, 999999)
        
        # 366일 범위인지 확인 (윤년)
        time_diff = (end_date - start_date).total_seconds()
        # 약 366일 = 31622400초
        assert 31622399 <= time_diff <= 31622401

    def test_get_year_range_utc_non_leap_year(self):
        """평년 범위 테스트"""
        start_date, end_date = get_year_range_utc(2023)  # 2023은 평년
        
        # 한국 시간 2023-01-01 00:00:00 -> UTC 2022-12-31 15:00:00
        assert start_date == datetime(2022, 12, 31, 15, 0, 0)
        # 한국 시간 2023-12-31 23:59:59.999999 -> UTC 2023-12-31 14:59:59.999999
        assert end_date == datetime(2023, 12, 31, 14, 59, 59, 999999)
        
        # 365일 범위인지 확인 (평년)
        time_diff = (end_date - start_date).total_seconds()
        # 약 365일 = 31536000초
        assert 31535999 <= time_diff <= 31536001

    def test_get_year_range_utc_timezone_naive(self):
        """반환된 datetime이 timezone naive인지 확인"""
        start_date, end_date = get_year_range_utc(2024)
        
        assert start_date.tzinfo is None
        assert end_date.tzinfo is None

    def test_get_year_range_utc_verifies_kst_to_utc_conversion(self):
        """KST -> UTC 변환 검증"""
        # 여러 연도 테스트
        test_cases = [
            (2020, datetime(2019, 12, 31, 15, 0, 0), datetime(2020, 12, 31, 14, 59, 59, 999999)),
            (2021, datetime(2020, 12, 31, 15, 0, 0), datetime(2021, 12, 31, 14, 59, 59, 999999)),
            (2022, datetime(2021, 12, 31, 15, 0, 0), datetime(2022, 12, 31, 14, 59, 59, 999999)),
            (2023, datetime(2022, 12, 31, 15, 0, 0), datetime(2023, 12, 31, 14, 59, 59, 999999)),
            (2024, datetime(2023, 12, 31, 15, 0, 0), datetime(2024, 12, 31, 14, 59, 59, 999999)),
        ]
        
        for year, expected_start, expected_end in test_cases:
            start_date, end_date = get_year_range_utc(year)
            assert start_date == expected_start, f"Failed for {year}: expected {expected_start}, got {start_date}"
            assert end_date == expected_end, f"Failed for {year}: expected {expected_end}, got {end_date}"

    def test_get_year_range_utc_full_year_coverage(self):
        """전체 연도가 올바르게 커버되는지 확인"""
        start_date, end_date = get_year_range_utc(2024)
        
        # 연도의 첫날과 마지막날이 범위에 포함되는지 확인
        # 한국 시간 2024-01-01의 UTC 변환값이 범위에 포함되어야 함
        jan_1_start, jan_1_end = parse_locdate_to_datetime_range("20240101")
        assert start_date <= jan_1_start <= end_date
        
        # 한국 시간 2024-12-31의 UTC 변환값이 범위에 포함되어야 함
        dec_31_start, dec_31_end = parse_locdate_to_datetime_range("20241231")
        assert start_date <= dec_31_start <= end_date
        assert start_date <= dec_31_end <= end_date

    def test_get_year_range_utc_consistency_with_locdate(self):
        """locdate 파싱과의 일관성 확인"""
        # 연도 범위의 시작은 해당 연도의 첫날 시작과 일치해야 함
        year_start, _ = get_year_range_utc(2024)
        jan_1_start, _ = parse_locdate_to_datetime_range("20240101")
        assert year_start == jan_1_start
        
        # 연도 범위의 끝은 해당 연도의 마지막날 끝과 일치해야 함
        _, year_end = get_year_range_utc(2024)
        _, dec_31_end = parse_locdate_to_datetime_range("20241231")
        assert year_end == dec_31_end

    def test_get_year_range_utc_historical_years(self):
        """과거 연도 테스트"""
        # 2000년 (윤년) - 최근 연도는 UTC+9 오프셋 사용
        start_2000, end_2000 = get_year_range_utc(2000)
        assert start_2000 == datetime(1999, 12, 31, 15, 0, 0)
        assert end_2000 == datetime(2000, 12, 31, 14, 59, 59, 999999)
        
        # 1900년 - 과거 연도는 타임존 오프셋이 다를 수 있으므로
        # 실제 반환값을 확인하고 그에 맞게 검증
        # (과거에는 UTC+8:30 또는 다른 오프셋을 사용했을 수 있음)
        start_1900, end_1900 = get_year_range_utc(1900)
        # 범위가 올바르게 생성되었는지 확인
        assert start_1900 < end_1900
        # 시작 날짜는 1900년 1월 1일 이전이어야 함 (KST -> UTC 변환)
        assert start_1900 < datetime(1900, 1, 1, 0, 0, 0)
        # 종료 날짜는 1900년 12월 31일 이후이어야 함 (KST -> UTC 변환)
        assert end_1900 > datetime(1900, 12, 31, 0, 0, 0)
        assert end_1900 < datetime(1901, 1, 1, 0, 0, 0)

    def test_get_year_range_utc_future_years(self):
        """미래 연도 테스트"""
        # 2100년 (평년)
        start_2100, end_2100 = get_year_range_utc(2100)
        assert start_2100 == datetime(2099, 12, 31, 15, 0, 0)
        assert end_2100 == datetime(2100, 12, 31, 14, 59, 59, 999999)
        
        # 2400년 (윤년, 400으로 나누어짐)
        start_2400, end_2400 = get_year_range_utc(2400)
        assert start_2400 == datetime(2399, 12, 31, 15, 0, 0)
        assert end_2400 == datetime(2400, 12, 31, 14, 59, 59, 999999)

    def test_parse_locdate_edge_cases(self):
        """locdate 파싱 엣지 케이스"""
        # 1월 1일
        start, end = parse_locdate_to_datetime_range("20240101")
        assert start == datetime(2023, 12, 31, 15, 0, 0)
        
        # 12월 31일
        start, end = parse_locdate_to_datetime_range("20241231")
        assert end == datetime(2024, 12, 31, 14, 59, 59, 999999)
        
        # 2월 29일 (윤년)
        start, end = parse_locdate_to_datetime_range("20240229")
        assert start == datetime(2024, 2, 28, 15, 0, 0)
        assert end == datetime(2024, 2, 29, 14, 59, 59, 999999)

    def test_parse_locdate_invalid_date_values(self):
        """잘못된 날짜 값 에러"""
        # 잘못된 월
        with pytest.raises(ValueError):
            parse_locdate_to_datetime_range("20240001")  # 월 00
        
        with pytest.raises(ValueError):
            parse_locdate_to_datetime_range("20241301")  # 월 13
        
        # 잘못된 일
        with pytest.raises(ValueError):
            parse_locdate_to_datetime_range("20240100")  # 일 00
        
        with pytest.raises(ValueError):
            parse_locdate_to_datetime_range("20240132")  # 일 32
        
        # 평년 2월 29일
        with pytest.raises(ValueError):
            parse_locdate_to_datetime_range("20230229")  # 2023은 평년

    def test_parse_locdate_with_whitespace(self):
        """공백이 포함된 locdate 에러"""
        with pytest.raises(ValueError):
            parse_locdate_to_datetime_range(" 20240101")  # 앞 공백
        
        with pytest.raises(ValueError):
            parse_locdate_to_datetime_range("20240101 ")  # 뒤 공백
        
        with pytest.raises(ValueError):
            parse_locdate_to_datetime_range("2024 0101")  # 중간 공백

    def test_parse_locdate_with_special_characters(self):
        """특수 문자가 포함된 locdate 에러"""
        with pytest.raises(ValueError):
            parse_locdate_to_datetime_range("2024-01-01")  # 하이픈
        
        with pytest.raises(ValueError):
            parse_locdate_to_datetime_range("2024/01/01")  # 슬래시
        
        with pytest.raises(ValueError):
            parse_locdate_to_datetime_range("2024.01.01")  # 점

