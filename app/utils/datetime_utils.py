"""
Datetime Utilities

datetime 변환 및 처리 유틸리티 함수들
- 검증(validation)이 아닌 변환(conversion) 함수들
- 모든 DB 구조에서 일관성 있게 작동하도록 UTC naive datetime으로 변환
"""
from datetime import datetime, timezone


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

