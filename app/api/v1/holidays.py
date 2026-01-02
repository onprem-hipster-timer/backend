"""
Holiday Router

조회는 동기 DB 세션을 사용하고, 데이터가 없을 때만 비동기 동기화를
백그라운드 태스크로 트리거합니다.
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.db.session import get_db
from app.domain.holiday.schema.dto import HolidayItem
from app.domain.holiday.service import HolidayReadService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/holidays", tags=["Holidays"])


@router.get("", response_model=list[HolidayItem])
async def get_holidays(
        year: Optional[int] = Query(None, description="조회 연도 (YYYY)"),
        start_year: Optional[int] = Query(None, description="시작 연도 (YYYY)"),
        end_year: Optional[int] = Query(None, description="종료 연도 (YYYY)"),
        auto_sync: bool = Query(
            False, description="데이터가 없을 경우 자동으로 동기화 실행"
        ),
        session: Session = Depends(get_db),
):
    """
    공휴일 조회 (DB에 있는 데이터만 반환)

    - year만 지정: 해당 연도 조회
    - start_year/end_year 지정: 범위 조회 (end_year 없으면 start_year로 대체)
    - 미지정: 현재 연도 조회
    - 데이터가 없고 auto_sync=True이면 비동기 동기화 태스크를 스케줄
    """
    if year:
        s, e = year, year
    elif start_year:
        s, e = start_year, end_year or start_year
    else:
        cur = datetime.now().year
        s, e = cur, cur

    read_service = HolidayReadService(session)
    return read_service.get_holidays(s, e, auto_sync=auto_sync)
