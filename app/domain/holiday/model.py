"""
Holiday Domain Model

SQLModel을 사용한 데이터베이스 모델 정의
"""
from datetime import datetime, UTC
from sqlmodel import SQLModel, Field, Column, String, UniqueConstraint

from app.models.base import UUIDBase, TimestampMixin


class HolidayModel(UUIDBase, TimestampMixin, table=True):
    """공휴일 정보 테이블"""
    __tablename__ = "holidays"
    
    date: datetime = Field(index=True)  # 날짜 (datetime 형식)
    dateName: str  # 국경일 명칭
    isHoliday: bool = Field(default=False)  # 공공기관 휴일 여부
    dateKind: str = Field(
        sa_column=Column(String(20), nullable=False, default="국경일")
    )  # 날짜 종류 (label: "국경일", "기념일", "24절기", "잡절")
    
    # 같은 날짜에 같은 이름의 공휴일은 중복 방지
    __table_args__ = (
        UniqueConstraint("date", "dateName", name="uq_holiday_date_name"),
    )


class HolidayHashModel(UUIDBase, TimestampMixin, table=True):
    """변경 감지용 해시 저장 테이블"""
    __tablename__ = "holiday_hashes"
    
    year: int = Field(unique=True, index=True)
    hash_value: str = Field(max_length=64)  # SHA256 해시

