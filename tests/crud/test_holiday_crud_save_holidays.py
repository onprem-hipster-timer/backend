"""
Holiday CRUD timezone 저장 회귀 테스트

테스트 목적:
- 세계 일정 서비스 기준으로 timezone 처리를 검증한다.
- crud.save_holidays()를 mock 없이 직접 호출한다.
- DB는 naive UTC(TIMESTAMP WITHOUT TIME ZONE)로 저장하므로,
  저장되는 datetime이 모두 timezone-naive UTC인지 검증한다.
- 입력으로 들어온 한국 표준시(KST) 날짜는 UTC로 변환된 뒤 naive로 저장된다.
- HolidayHashModel.updated_at에 aware datetime을 주입하면 PostgreSQL asyncpg에서
  타입 충돌(#41)이 발생하므로, 반드시 naive UTC로 저장되어야 한다.

중요:
- 이 테스트는 SQLite보다 PostgreSQL 테스트 DB에서 실행하는 것이 정확하다.
- SQLite는 timezone 타입을 엄격히 검증하지 않기 때문에 운영 장애를 재현하지 못할 수 있다.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.crud.holiday import (
    get_holiday_by_date,
    get_holiday_hash,
    save_holidays,
)
from app.domain.holiday.schema.dto import HolidayItem
from app.models.holiday import HolidayHashModel, HolidayModel


def _make_holiday_item(
    *,
    locdate: str = "20240101",
    seq: int = 1,
    dateKind: str = "01",
    dateName: str = "신정",
    isHoliday: bool = True,
) -> HolidayItem:
    return HolidayItem(
        locdate=locdate,
        seq=seq,
        dateKind=dateKind,
        dateName=dateName,
        isHoliday=isHoliday,
    )


def _assert_utc_naive(value: datetime | None) -> None:
    """DB에 저장된 datetime이 timezone-naive UTC인지 검증한다."""
    assert value is not None
    assert isinstance(value, datetime)
    # DB는 TIMESTAMP WITHOUT TIME ZONE이므로 tzinfo가 없어야 한다.
    assert value.tzinfo is None


@pytest.mark.asyncio
async def test_save_holidays_creates_holidays_with_naive_utc_datetimes(
    test_async_session,
):
    """
    목적 객체:
    - crud.save_holidays()

    검증:
    - HolidayModel.start_date/end_date가 timezone-naive UTC로 저장된다.
    - 입력 KST 날짜가 UTC로 변환된다. (KST 2024-01-01 00:00 -> UTC 2023-12-31 15:00)
    - locdate는 Asia/Seoul 기준 날짜로 다시 계산된다.
    """
    hash_value = "a" * 64

    holidays = [
        _make_holiday_item(
            locdate="20240101",
            dateKind="01",
            dateName="신정",
            isHoliday=True,
        )
    ]

    await save_holidays(
        session=test_async_session,
        year=2024,
        holidays=holidays,
        hash_value=hash_value,
    )

    await test_async_session.flush()

    stmt = select(HolidayModel).where(HolidayModel.dateName == "신정")
    result = await test_async_session.execute(stmt)
    saved_holiday = result.scalar_one_or_none()

    assert saved_holiday is not None
    assert saved_holiday.dateName == "신정"
    assert saved_holiday.dateKind == "국경일"
    assert saved_holiday.isHoliday is True

    _assert_utc_naive(saved_holiday.start_date)
    _assert_utc_naive(saved_holiday.end_date)

    # KST 기준 24시간 범위가 UTC naive로 변환되어 저장된다.
    assert saved_holiday.start_date == datetime(2023, 12, 31, 15, 0, 0)
    assert saved_holiday.end_date == datetime(2024, 1, 1, 14, 59, 59, 999999)

    # locdate는 UTC naive를 다시 KST로 환산한 날짜다.
    assert saved_holiday.locdate == "20240101"

    hash_stmt = select(HolidayHashModel).where(HolidayHashModel.year == 2024)
    hash_result = await test_async_session.execute(hash_stmt)
    saved_hash = hash_result.scalar_one_or_none()

    assert saved_hash is not None
    assert saved_hash.hash_value == hash_value

    _assert_utc_naive(saved_hash.created_at)
    _assert_utc_naive(saved_hash.updated_at)


@pytest.mark.asyncio
async def test_save_holidays_updates_existing_hash_with_naive_utc_updated_at(
    test_async_session,
):
    """
    목적 객체:
    - crud.save_holidays()
    - HolidayHashModel.updated_at
    - TimestampMixin

    검증:
    - 기존 HolidayHashModel이 있을 때 hash_value를 갱신한다.
    - updated_at은 timezone-naive UTC datetime이다.
    - flush가 성공한다.

    기존 운영 장애(#41)는 이 경로에서 aware datetime을 naive 컬럼에 주입하여 발생했다.
    """
    old_hash = "a" * 64
    new_hash = "b" * 64

    existing_hash = HolidayHashModel(
        year=2024,
        hash_value=old_hash,
    )
    test_async_session.add(existing_hash)
    await test_async_session.flush()

    _assert_utc_naive(existing_hash.created_at)
    _assert_utc_naive(existing_hash.updated_at)

    holidays = [
        _make_holiday_item(
            locdate="20240101",
            dateKind="01",
            dateName="신정",
            isHoliday=True,
        )
    ]

    await save_holidays(
        session=test_async_session,
        year=2024,
        holidays=holidays,
        hash_value=new_hash,
    )

    assert existing_hash.hash_value == new_hash

    # 핵심 검증:
    # DB는 naive UTC로 저장하므로 updated_at은 timezone-naive여야 한다.
    # aware datetime이면 PostgreSQL asyncpg에서 flush가 실패한다.
    _assert_utc_naive(existing_hash.updated_at)

    # 실제 flush까지 성공해야 한다.
    await test_async_session.flush()

    await test_async_session.refresh(existing_hash)

    assert existing_hash.hash_value == new_hash
    _assert_utc_naive(existing_hash.updated_at)


@pytest.mark.asyncio
async def test_save_holidays_hash_update_allows_following_query_autoflush(
    test_async_session,
):
    """
    목적 객체:
    - crud.save_holidays()
    - get_holiday_hash()

    검증:
    - 기존 hash row를 업데이트한 뒤,
      같은 세션에서 다음 SELECT가 실행되어도 autoflush 오류가 나지 않는다.

    운영 장애 흐름(#41):
    1. 특정 연도 hash row 업데이트
    2. commit 전 같은 세션에서 다음 연도 hash 조회
    3. SELECT 전에 SQLAlchemy autoflush 발생
    4. DB 컬럼 타입(naive)과 datetime 타입(aware)이 맞지 않으면 실패
    """
    old_hash_2027 = "c" * 64
    new_hash_2027 = "d" * 64

    existing_hash_2027 = HolidayHashModel(
        year=2027,
        hash_value=old_hash_2027,
    )
    test_async_session.add(existing_hash_2027)
    await test_async_session.flush()

    holidays_2027 = [
        _make_holiday_item(
            locdate="20270101",
            dateKind="01",
            dateName="신정",
            isHoliday=True,
        )
    ]

    await save_holidays(
        session=test_async_session,
        year=2027,
        holidays=holidays_2027,
        hash_value=new_hash_2027,
    )

    assert existing_hash_2027.hash_value == new_hash_2027
    _assert_utc_naive(existing_hash_2027.updated_at)

    # SELECT 실행 전 autoflush가 발생한다.
    # naive UTC로 맞춰져 있으면 실패하지 않아야 한다.
    hash_2026 = await get_holiday_hash(test_async_session, 2026)

    assert hash_2026 is None


@pytest.mark.asyncio
async def test_get_holiday_by_date_accepts_timezone_aware_kst_datetime(
    test_async_session,
):
    """
    목적 객체:
    - crud.save_holidays()
    - crud.get_holiday_by_date()

    검증:
    - KST timezone-aware datetime으로 조회할 수 있다.
    - 내부적으로 UTC naive datetime으로 변환되어 범위 조회된다.
    """
    hash_value = "e" * 64

    holidays = [
        _make_holiday_item(
            locdate="20240101",
            dateKind="01",
            dateName="신정",
            isHoliday=True,
        )
    ]

    await save_holidays(
        session=test_async_session,
        year=2024,
        holidays=holidays,
        hash_value=hash_value,
    )
    await test_async_session.flush()

    kst = ZoneInfo("Asia/Seoul")
    kst_datetime = datetime(
        2024,
        1,
        1,
        12,
        0,
        0,
        tzinfo=kst,
    )

    result = await get_holiday_by_date(test_async_session, kst_datetime)

    assert result is not None
    assert result.dateName == "신정"
    assert result.locdate == "20240101"


@pytest.mark.asyncio
async def test_get_holiday_by_date_accepts_naive_datetime_as_utc(
    test_async_session,
):
    """
    목적 객체:
    - crud.get_holiday_by_date()
    - ensure_utc_naive()

    검증:
    - get_holiday_by_date는 내부에서 parse_locdate_to_datetime_range로 이미 UTC naive로
      변환된 값을 받으므로, naive 입력을 UTC로 가정하여 그대로 범위 조회한다.
      (입력 경계의 KST 가정은 이 저수준 조회 함수가 아니라 호출 경로에서 처리한다.)
    - 저장된 신정의 UTC naive 범위 내 시각으로 조회하면 매칭된다.
      (UTC 2023-12-31 15:00 ~ 2024-01-01 14:59:59.999999)
    """
    hash_value = "e" * 64

    holidays = [
        _make_holiday_item(
            locdate="20240101",
            dateKind="01",
            dateName="신정",
            isHoliday=True,
        )
    ]

    await save_holidays(
        session=test_async_session,
        year=2024,
        holidays=holidays,
        hash_value=hash_value,
    )
    await test_async_session.flush()

    # UTC naive 자정 (KST 09:00에 해당) → 저장된 신정 범위 내
    naive_utc_datetime = datetime(2024, 1, 1, 0, 0, 0)

    result = await get_holiday_by_date(test_async_session, naive_utc_datetime)

    assert result is not None
    assert result.dateName == "신정"
    assert result.locdate == "20240101"


@pytest.mark.asyncio
async def test_save_holidays_replaces_existing_holidays_for_same_year_with_naive_dates(
    test_async_session,
):
    """
    목적 객체:
    - crud.save_holidays()

    검증:
    - 같은 연도의 기존 HolidayModel을 삭제하고 새 데이터로 교체한다.
    - 새로 저장된 start_date/end_date도 timezone-naive UTC이다.
    """
    first_hash = "f" * 64
    second_hash = "1" * 64

    first_holidays = [
        _make_holiday_item(
            locdate="20240101",
            dateKind="01",
            dateName="신정",
            isHoliday=True,
        )
    ]

    await save_holidays(
        session=test_async_session,
        year=2024,
        holidays=first_holidays,
        hash_value=first_hash,
    )
    await test_async_session.flush()

    second_holidays = [
        _make_holiday_item(
            locdate="20240301",
            dateKind="01",
            dateName="삼일절",
            isHoliday=True,
        )
    ]

    await save_holidays(
        session=test_async_session,
        year=2024,
        holidays=second_holidays,
        hash_value=second_hash,
    )
    await test_async_session.flush()

    stmt = select(HolidayModel)
    result = await test_async_session.execute(stmt)
    saved_holidays = list(result.scalars().all())

    assert len(saved_holidays) == 1

    saved_holiday = saved_holidays[0]

    assert saved_holiday.dateName == "삼일절"
    assert saved_holiday.locdate == "20240301"

    _assert_utc_naive(saved_holiday.start_date)
    _assert_utc_naive(saved_holiday.end_date)
    # KST 2024-03-01 00:00 -> UTC 2024-02-29 15:00 (2024는 윤년)
    assert saved_holiday.start_date == datetime(2024, 2, 29, 15, 0, 0)

    hash_stmt = select(HolidayHashModel).where(HolidayHashModel.year == 2024)
    hash_result = await test_async_session.execute(hash_stmt)
    saved_hash = hash_result.scalar_one()

    assert saved_hash.hash_value == second_hash
    _assert_utc_naive(saved_hash.updated_at)
