"""
Datetime Utilities

datetime 변환 및 처리 유틸리티 함수들
- 검증(validation)이 아닌 변환(conversion) 함수들
- 모든 DB 구조에서 일관성 있게 작동하도록 UTC naive datetime으로 변환
"""
from datetime import datetime, timedelta, timezone


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


# 기본 시간 허용 오차 (1분)
DEFAULT_TIME_TOLERANCE_SECONDS = 60


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

