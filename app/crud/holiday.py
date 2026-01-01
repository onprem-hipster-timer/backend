"""
Holiday CRUD

FastAPI Best Practices:
- commit은 호출자가 처리
- CRUD는 데이터 접근만 담당
- 비동기 AsyncSession 사용
"""
import logging
from datetime import datetime, UTC
from typing import Optional

from sqlalchemy import delete, extract, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Session

from app.domain.holiday.enums import DateKind
from app.domain.holiday.model import HolidayModel, HolidayHashModel
from app.domain.holiday.schema.dto import HolidayItem

logger = logging.getLogger(__name__)


def _parse_locdate_to_datetime(locdate: str) -> datetime:
    """
    locdate 문자열(YYYYMMDD)을 datetime으로 변환
    
    :param locdate: 날짜 문자열 (YYYYMMDD)
    :return: datetime 객체 (UTC naive)
    """
    year = int(locdate[0:4])
    month = int(locdate[4:6])
    day = int(locdate[6:8])
    return datetime(year, month, day, tzinfo=None)


def _parse_datekind_to_label(datekind_str: str) -> str:
    """
    dateKind 문자열을 label로 변환
    
    :param datekind_str: dateKind 문자열 ("01", "02", "03", "04")
    :return: dateKind label ("국경일", "기념일", "24절기", "잡절")
    :raises ValueError: 알 수 없는 dateKind 값인 경우
    """
    date_kind_enum = DateKind(datekind_str)
    return date_kind_enum.label


async def get_holiday_hash(session: AsyncSession, year: int) -> Optional[str]:
    """
    저장된 해시 조회
    
    :param session: AsyncSession
    :param year: 연도
    :return: 해시 값 또는 None
    """
    stmt = select(HolidayHashModel).where(HolidayHashModel.year == year)
    result = await session.execute(stmt)
    hash_model = result.scalar_one_or_none()
    return hash_model.hash_value if hash_model else None


async def get_holidays_by_year(
    session: AsyncSession, start_year: int, end_year: Optional[int] = None
) -> list[HolidayModel]:
    """
    연도별 공휴일 조회 (단일 연도 또는 범위)
    
    :param session: AsyncSession
    :param start_year: 시작 연도
    :param end_year: 종료 연도 (포함). None이면 start_year과 동일하게 처리 (단일 연도 조회)
    :return: 공휴일 모델 리스트
    """
    # end_year가 지정되지 않으면 start_year과 동일하게 처리
    if end_year is None:
        end_year = start_year
    
    if start_year == end_year:
        # 단일 연도 조회
        stmt = select(HolidayModel).where(extract("year", HolidayModel.date) == start_year)
    else:
        # 범위 조회
        stmt = select(HolidayModel).where(
            extract("year", HolidayModel.date) >= start_year,
            extract("year", HolidayModel.date) <= end_year
        )
    
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ============ 동기 조회 전용 (API 조회용) ============
def get_holidays_by_year_sync(
    session: Session, start_year: int, end_year: Optional[int] = None
) -> list[HolidayModel]:
    """
    연도별 공휴일 조회 (단일 연도 또는 범위) - 동기 버전

    - API 조회용 (외부 호출 없이 DB 조회만)
    - commit/rollback은 호출자가 관리
    """
    if end_year is None:
        end_year = start_year

    if start_year == end_year:
        stmt = select(HolidayModel).where(extract("year", HolidayModel.date) == start_year)
    else:
        stmt = select(HolidayModel).where(
            extract("year", HolidayModel.date) >= start_year,
            extract("year", HolidayModel.date) <= end_year,
        )

    result = session.exec(stmt)
    return list(result.all())


async def get_holiday_by_date(
        session: AsyncSession, date: datetime
) -> Optional[HolidayModel]:
    """
    날짜로 공휴일 조회
    
    :param session: AsyncSession
    :param date: 날짜 (datetime)
    :return: 공휴일 모델 또는 None
    """
    # 날짜를 UTC naive로 변환 (시간 부분 제거)
    date_naive = date.replace(hour=0, minute=0, second=0, microsecond=0)
    if date_naive.tzinfo:
        date_naive = date_naive.astimezone(UTC).replace(tzinfo=None)

    stmt = select(HolidayModel).where(HolidayModel.date == date_naive)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def save_holidays(
        session: AsyncSession,
        year: int,
        holidays: list[HolidayItem],
        hash_value: str,
) -> None:
    """
    공휴일 저장 (업데이트 포함)
    
    트랜잭션:
    1. 기존 해시 모델 조회 (삭제 전에 미리 조회하여 autoflush 방지)
    2. 기존 데이터 삭제
    3. 새 데이터 삽입
    4. 해시 저장/업데이트
    
    FastAPI Best Practices:
    - commit은 호출자가 처리
    - CRUD는 데이터 접근만 담당 (비즈니스 로직 제외)
    
    :param session: AsyncSession
    :param year: 연도
    :param holidays: 공휴일 항목 리스트
    :param hash_value: 해시 값
    """
    # 1. 기존 해시 모델 조회 (삭제 전에 미리 조회하여 autoflush 방지)
    hash_stmt = select(HolidayHashModel).where(
        HolidayHashModel.year == year
    )
    hash_result = await session.execute(hash_stmt)
    hash_model = hash_result.scalar_one_or_none()

    # 2. 기존 데이터 삭제 (해당 연도의 모든 데이터)
    delete_stmt = delete(HolidayModel).where(
        extract("year", HolidayModel.date) == year
    )
    await session.execute(delete_stmt)
    await session.flush()  # 삭제를 즉시 DB에 반영

    # 3. 새 데이터 삽입
    for item in holidays:
        # locdate 문자열을 datetime으로 변환
        date = _parse_locdate_to_datetime(item.locdate)

        # dateKind를 label로 변환 ("01" -> "국경일")
        date_kind_label = _parse_datekind_to_label(item.dateKind)

        holiday = HolidayModel(
            date=date,
            dateName=item.dateName,
            isHoliday=item.isHoliday,
            dateKind=date_kind_label,
        )
        session.add(holiday)

    # 4. 해시 저장/업데이트 (이미 조회한 hash_model 사용)
    now = datetime.now(UTC)
    if hash_model:
        hash_model.hash_value = hash_value
        hash_model.updated_at = now
    else:
        hash_model = HolidayHashModel(
            year=year,
            hash_value=hash_value,
        )
        session.add(hash_model)

    # commit은 호출자가 처리
    logger.info(
        f"Saved {len(holidays)} holidays for year {year} "
        f"(hash: {hash_value[:8]}...)"
    )
