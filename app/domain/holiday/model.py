"""
Holiday Domain Model

SQLModel을 사용한 데이터베이스 모델 정의
"""
from datetime import datetime

from sqlmodel import Field, Column, String, UniqueConstraint

from app.models.base import UUIDBase, TimestampMixin


class HolidayModel(UUIDBase, TimestampMixin, table=True):
    """공휴일 정보 테이블"""
    __tablename__ = "holidays"

    start_date: datetime = Field(index=True)  # 시작 날짜 (한국 표준시 기준 날짜의 시작, UTC naive)
    end_date: datetime = Field(index=True)  # 종료 날짜 (한국 표준시 기준 날짜의 종료, UTC naive)
    dateName: str  # 국경일 명칭
    isHoliday: bool = Field(default=False)  # 공공기관 휴일 여부
    dateKind: str = Field(
        sa_column=Column(String(20), nullable=False)
    )  # 날짜 종류 (label: "국경일", "기념일", "24절기", "잡절")

    # 같은 날짜 범위에 같은 이름의 공휴일은 중복 방지
    __table_args__ = (
        UniqueConstraint("start_date", "end_date", "dateName", name="uq_holiday_date_range_name"),
    )

    @property
    def locdate(self) -> str:
        """start_date를 기준으로 YYYYMMDD 형식으로 변환 (한국 시간 기준 날짜)"""
        # UTC naive datetime을 한국 시간으로 변환하여 날짜 추출
        from zoneinfo import ZoneInfo
        from datetime import timezone as tz
        
        # UTC로 가정하고 한국 시간으로 변환
        utc_aware = self.start_date.replace(tzinfo=tz.utc)
        kst_aware = utc_aware.astimezone(ZoneInfo("Asia/Seoul"))
        return kst_aware.strftime("%Y%m%d")

    @property
    def seq(self) -> int:
        """seq는 DB에 없으므로 0 반환"""
        return 0


class HolidayHashModel(UUIDBase, TimestampMixin, table=True):
    """변경 감지용 해시 저장 테이블"""
    __tablename__ = "holiday_hashes"

    year: int = Field(unique=True, index=True)
    hash_value: str = Field(max_length=64)  # SHA256 해시
