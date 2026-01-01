"""
Dateutil Domain Service

datetime 변환 및 타임존 처리 서비스
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from app.domain.dateutil.exceptions import InvalidTimezoneError

# 기본 시간 허용 오차 (1분)
DEFAULT_TIME_TOLERANCE_SECONDS = 60


def to_utc_naive(dt: datetime | None) -> datetime | None:
    """
    datetime을 UTC naive datetime으로 변환

    모든 DB 구조에서 일관성 있게 작동:
    - SQLite: timezone 정보를 저장하지 않으므로 naive datetime 필요
    - PostgreSQL: timezone 정보를 저장할 수 있지만, UTC로 통일하여 저장

    비즈니스 로직:
    - timezone이 있으면 UTC로 변환 후 naive datetime으로 변환
    - timezone이 없으면 그대로 반환 (UTC로 가정)

    :param dt: datetime 객체 (timezone 있거나 없음)
    :return: UTC naive datetime (timezone 정보 제거)
    """
    if dt is None:
        return None

    # timezone이 있으면 UTC로 변환
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)

    # timezone 정보 제거 (naive datetime)
    return dt.replace(tzinfo=None)


def ensure_utc_naive(dt: datetime | None) -> datetime | None:
    """
    datetime이 UTC naive인지 보장하고 변환

    비즈니스 로직:
    - timezone이 있으면 UTC로 변환 후 naive datetime으로 변환
    - timezone이 없으면 그대로 반환 (UTC로 가정)
    - 모든 datetime은 UTC naive로 저장되어야 함

    :param dt: datetime 객체
    :return: UTC naive datetime
    """
    if dt is None:
        return None

    # timezone이 있으면 UTC로 변환
    if dt.tzinfo is not None:
        # UTC가 아니면 자동으로 UTC로 변환
        if dt.tzinfo != timezone.utc:
            dt = dt.astimezone(timezone.utc)
        # UTC로 변환 후 naive datetime으로 변환
        return dt.replace(tzinfo=None)

    # timezone이 없으면 그대로 반환 (UTC로 가정)
    return dt


def convert_utc_naive_to_timezone(
        dt: datetime | None,
        tz: timezone | str | None
) -> datetime | None:
    """
    UTC naive datetime을 지정된 타임존의 aware datetime으로 변환

    모든 datetime은 UTC naive로 저장되므로, 클라이언트가 요청한 타임존으로 변환합니다.

    :param dt: UTC naive datetime 객체
    :param tz: 변환할 타임존 (timezone 객체, 문자열, 또는 None)
    :return: 지정된 타임존의 aware datetime
    """
    if dt is None:
        return None

    # 타임존이 없으면 그대로 반환
    if tz is None:
        return dt

    # 문자열인 경우 파싱
    if isinstance(tz, str):
        tz = parse_timezone(tz)

    # UTC naive datetime을 UTC aware datetime으로 변환
    utc_aware = dt.replace(tzinfo=timezone.utc)

    # 지정된 타임존으로 변환
    return utc_aware.astimezone(tz)


def format_datetime_for_rrule(dt: datetime) -> str:
    """
    RRULE UNTIL 형식으로 datetime 변환

    UTC naive datetime을 RRULE의 UNTIL 형식으로 변환합니다.
    UTC naive datetime이므로 'Z' 접미사는 붙이지 않습니다.

    :param dt: UTC naive datetime 객체
    :return: RRULE UNTIL 형식 문자열 (예: "20240129T235959")
    """
    return dt.strftime('%Y%m%dT%H%M%S')


def is_datetime_within_tolerance(
        dt1: datetime,
        dt2: datetime,
        tolerance_seconds: int = DEFAULT_TIME_TOLERANCE_SECONDS,
) -> bool:
    """
    두 datetime이 허용 오차 내에 있는지 확인

    시간 정밀도 문제를 방지하기 위해 약간의 허용 오차를 둡니다.
    주로 반복 일정의 예외 인스턴스 매칭에 사용됩니다.

    :param dt1: 첫 번째 datetime
    :param dt2: 두 번째 datetime
    :param tolerance_seconds: 허용 오차 (초 단위, 기본값: 60초)
    :return: 허용 오차 내에 있으면 True, 아니면 False
    """
    time_diff = abs((dt1 - dt2).total_seconds())
    return time_diff <= tolerance_seconds


def get_datetime_range(
        dt: datetime,
        tolerance_seconds: int = DEFAULT_TIME_TOLERANCE_SECONDS,
) -> tuple[datetime, datetime]:
    """
    datetime 주변의 범위 계산 (DB 쿼리용)

    특정 datetime을 중심으로 허용 오차 범위를 계산합니다.
    DB 쿼리에서 시간 정밀도 문제를 해결하기 위해 사용됩니다.

    :param dt: 기준 datetime
    :param tolerance_seconds: 허용 오차 (초 단위, 기본값: 60초)
    :return: (시작 범위, 종료 범위) 튜플
    """
    start_range = dt - timedelta(seconds=tolerance_seconds)
    end_range = dt + timedelta(seconds=tolerance_seconds)
    return (start_range, end_range)


def get_year_range_utc(year: int) -> tuple[datetime, datetime]:
    """
    한국 표준시 기준 연도 범위를 UTC naive datetime으로 변환

    한국 표준시(KST, UTC+9) 기준으로 해당 연도의 시작과 끝을 UTC로 변환합니다.
    DB에는 UTC naive datetime이 저장되어 있으므로, 한국 시간 기준
    연도 범위를 UTC로 변환하여 비교해야 정확한 결과가 나옵니다.

    :param year: 연도 (한국 표준시 기준)
    :return: (시작 datetime, 종료 datetime) 튜플 (UTC naive)
    """
    kst = ZoneInfo("Asia/Seoul")
    # 한국 시간 기준 해당 연도 1월 1일 00:00:00
    kst_start = datetime(year, 1, 1, 0, 0, 0, 0, tzinfo=kst)
    # 한국 시간 기준 해당 연도 12월 31일 23:59:59.999999
    kst_end = datetime(year, 12, 31, 23, 59, 59, 999999, tzinfo=kst)

    utc_start = ensure_utc_naive(kst_start)
    utc_end = ensure_utc_naive(kst_end)

    return (utc_start, utc_end)


def parse_locdate_to_datetime_range(locdate: str) -> tuple[datetime, datetime]:
    """
    locdate 문자열(YYYYMMDD)을 한국 표준시(KST) 기준 24시간 범위로 변환
    
    한국천문연구원 특일 정보제공 서비스에서 사용하는 날짜 형식을 파싱합니다.
    locdate는 한국 표준시(KST, UTC+9) 기준 날짜로 해석됩니다.
    예: "20240101"은 한국 시간 기준 2024년 1월 1일 00:00:00 ~ 23:59:59.999999를 의미하며,
    이를 UTC로 변환한 후 naive datetime 범위로 반환합니다.
    
    :param locdate: 날짜 문자열 (YYYYMMDD 형식, 예: "20240101")
    :return: (start_datetime, end_datetime) 튜플 (UTC naive datetime, 한국 시간 기준 24시간 범위)
    :raises ValueError: 잘못된 날짜 형식인 경우
    """
    if len(locdate) != 8:
        raise ValueError(f"Invalid locdate format: {locdate}. Expected YYYYMMDD format (8 digits)")
    
    try:
        year = int(locdate[0:4])
        month = int(locdate[4:6])
        day = int(locdate[6:8])
        
        # 한국 표준시(KST, UTC+9) 기준으로 날짜 해석
        kst = ZoneInfo("Asia/Seoul")
        
        # 시작 시간: 한국 시간 기준 해당 날짜 00:00:00
        kst_start = datetime(year, month, day, 0, 0, 0, 0, tzinfo=kst)
        # 종료 시간: 한국 시간 기준 해당 날짜 23:59:59.999999
        kst_end = datetime(year, month, day, 23, 59, 59, 999999, tzinfo=kst)
        
        # UTC로 변환 후 naive datetime으로 변환 (ensure_utc_naive 사용)
        utc_start = ensure_utc_naive(kst_start)
        utc_end = ensure_utc_naive(kst_end)
        
        return (utc_start, utc_end)
    except (ValueError, IndexError) as e:
        raise ValueError(f"Invalid locdate format: {locdate}. {str(e)}")


def parse_timezone(tz_str: Optional[str]) -> Optional[timezone]:
    """
    타임존 문자열을 timezone 객체로 변환
    
    지원 형식:
    - "UTC" 또는 None: UTC
    - "+09:00", "-05:00", "+09:00:30": UTC offset 형식 (초 단위 선택)
    - "Asia/Seoul" 등: 타임존 이름 (zoneinfo 사용, Python 3.9+ 필수)
    
    :param tz_str: 타임존 문자열
    :return: timezone 객체 또는 None (UTC)
    :raises InvalidTimezoneError: 잘못된 타임존 형식
    """
    if tz_str is None or tz_str.upper() == "UTC":
        return timezone.utc

    # UTC offset 형식 (+09:00, -05:00, +09:00:30 등)
    if tz_str.startswith(("+", "-")):
        sign = -1 if tz_str[0] == "-" else 1
        parts = tz_str[1:].split(":")

        try:
            # "+09:00:30" -> hours=9, minutes=0, seconds=30
            hours = int(parts[0])
            minutes = int(parts[1]) if len(parts) > 1 else 0
            seconds = int(parts[2]) if len(parts) > 2 else 0
            offset = timedelta(hours=hours * sign, minutes=minutes * sign, seconds=seconds * sign)
            return timezone(offset)
        except (ValueError, IndexError):
            raise InvalidTimezoneError(
                detail=f"Invalid timezone offset format: {tz_str}. Use format like +09:00 or +09:00:30"
            )

    # 타임존 이름 (예: "Asia/Seoul", "America/New_York")
    try:
        return ZoneInfo(tz_str)
    except (KeyError, ValueError):
        # ZoneInfoNotFoundError는 KeyError를 상속하거나 ValueError를 발생시킬 수 있음
        # 또는 타임존 이름이 잘못된 경우
        raise InvalidTimezoneError(
            detail=f"Invalid timezone name: {tz_str}. Make sure tzdata package is installed."
        )
