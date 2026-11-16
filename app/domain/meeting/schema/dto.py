"""
Meeting Domain DTO (Data Transfer Objects)

일정 조율 관련 데이터 전송 객체
"""
import unicodedata
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional, List
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil.relativedelta import relativedelta
from pydantic import ConfigDict, field_validator, model_validator
from pydantic.experimental.missing_sentinel import MISSING

from app.core.base_model import CustomModel
from app.domain.dateutil.service import convert_utc_naive_to_timezone, ensure_utc_naive
from app.models.visibility import VisibilityLevel
from app.utils.validators import validate_time_order


TITLE_MAX_LENGTH = 200
DESCRIPTION_MAX_LENGTH = 2000
MAX_PERIOD = relativedelta(months=3)
TIME_SLOT_MINUTES_MIN = 5
TIME_SLOT_MINUTES_MAX = 1440


def daily_range(start_time: time, end_time: time) -> timedelta:
    """하루 범위 [start_time, end_time). end_time 00:00은 다음 날 00:00(하루의 끝)이다"""
    end = datetime.combine(date.min + timedelta(days=1 if end_time == time(0) else 0), end_time)
    return end - datetime.combine(date.min, start_time)


def _validate_title(v: str) -> str:
    """앞뒤 공백을 뺀 1–200자"""
    v = v.strip()
    if not 1 <= len(v) <= TITLE_MAX_LENGTH:
        raise ValueError(f"title must be 1-{TITLE_MAX_LENGTH} characters after trimming")
    return v


def _validate_description(v: str | None) -> str | None:
    if v is not None and len(v) > DESCRIPTION_MAX_LENGTH:
        raise ValueError(f"description must be at most {DESCRIPTION_MAX_LENGTH} characters")
    return v


def _validate_available_days(v: list[int]) -> list[int]:
    """요일 리스트 검증 (0-6, 중복 불가, 1개 이상)"""
    if not isinstance(v, list):
        raise ValueError("available_days must be a list")
    if not v:
        raise ValueError("available_days must not be empty")
    if not all(isinstance(d, int) and 0 <= d <= 6 for d in v):
        raise ValueError("available_days must contain integers 0-6")
    if len(set(v)) != len(v):
        raise ValueError("available_days must not contain duplicates")
    return sorted(v)


def _validate_timezone(v: str) -> str:
    """IANA 시간대 이름 (예: Asia/Seoul, UTC). UTC 오프셋 문자열은 받지 않는다"""
    try:
        ZoneInfo(v)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("timezone must be an IANA time zone name such as Asia/Seoul or UTC") from None
    return v


def _validate_time_slot_minutes(v: int) -> int:
    if not TIME_SLOT_MINUTES_MIN <= v <= TIME_SLOT_MINUTES_MAX:
        raise ValueError(
            f"time_slot_minutes must be between {TIME_SLOT_MINUTES_MIN} and {TIME_SLOT_MINUTES_MAX}"
        )
    return v


class MeetingCreate(CustomModel):
    """일정 조율 생성 DTO

    수정(PATCH) 때도 저장된 값에 수정 내용을 합쳐 이 DTO로 다시 검증한다 (MeetingService.update_meeting).
    """
    title: str
    description: Optional[str] = None
    start_date: date
    end_date: date
    timezone: str  # 날짜·요일·시간을 해석하는 IANA 시간대
    available_days: List[int]  # 요일 리스트 (0-6, 0=월요일)
    start_time: time  # 하루 시작 시간
    end_time: time  # 하루 종료 시간 (포함하지 않음, 00:00이면 하루의 끝)
    time_slot_minutes: int = 30  # 시간 선택 단위 (분)
    allow_guests: bool = False  # 게스트를 받는지. true는 공개 범위가 public일 때만 (MeetingService)

    @field_validator("title")
    @classmethod
    def validate_title(cls, v):
        return _validate_title(v)

    @field_validator("description")
    @classmethod
    def validate_description(cls, v):
        return _validate_description(v)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v):
        return _validate_timezone(v)

    @field_validator("available_days")
    @classmethod
    def validate_available_days(cls, v):
        """요일 리스트 검증"""
        return _validate_available_days(v)

    @field_validator("end_date")
    @classmethod
    def validate_date_range(cls, v, info):
        """날짜 범위 검증"""
        start_date = info.data.get("start_date")
        if start_date and v < start_date:
            raise ValueError("end_date must be >= start_date")
        return v

    @field_validator("end_time")
    @classmethod
    def validate_time_range(cls, v, info):
        """시간 범위 검증"""
        start_time = info.data.get("start_time")
        if start_time is not None and v != time(0) and v <= start_time:
            raise ValueError("end_time must be > start_time or 00:00 (end of day)")
        return v

    @field_validator("time_slot_minutes")
    @classmethod
    def validate_time_slot_minutes(cls, v):
        """시간 슬롯 단위 검증"""
        return _validate_time_slot_minutes(v)

    @model_validator(mode="after")
    def validate_shape(self):
        """기간은 start_date + 3개월(같은 날, 없으면 그 달 말일)까지, 시간 단위는 하루 범위 이하"""
        if self.end_date > self.start_date + MAX_PERIOD:
            raise ValueError("end_date must be no later than 3 months after start_date")
        if self.time_slot_minutes * 60 > daily_range(self.start_time, self.end_time).total_seconds():
            raise ValueError("time_slot_minutes must not exceed end_time - start_time")
        return self


class MeetingUpdate(CustomModel):
    """일정 조율 업데이트 DTO"""
    title: str | None = MISSING
    description: str | None = MISSING
    start_date: date | None = MISSING
    end_date: date | None = MISSING
    timezone: str = MISSING
    available_days: list[int] | None = MISSING
    start_time: time | None = MISSING
    end_time: time | None = MISSING
    time_slot_minutes: int | None = MISSING
    allow_guests: bool = MISSING

    @field_validator("title")
    @classmethod
    def validate_title(cls, v):
        if isinstance(v, str):
            return _validate_title(v)
        return v

    @field_validator("description")
    @classmethod
    def validate_description(cls, v):
        return _validate_description(v)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v):
        return _validate_timezone(v)

    @field_validator("available_days")
    @classmethod
    def validate_available_days(cls, v):
        """요일 리스트 검증"""
        if v is not None:
            return _validate_available_days(v)
        return v

    @field_validator("time_slot_minutes")
    @classmethod
    def validate_time_slot_minutes(cls, v):
        """시간 슬롯 단위 검증"""
        if v is not None:
            return _validate_time_slot_minutes(v)
        return v


class MeetingRead(CustomModel):
    """일정 조율 조회 DTO"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: str
    title: str
    description: Optional[str] = None
    start_date: date
    end_date: date
    timezone: str
    available_days: List[int]
    start_time: time
    end_time: time
    time_slot_minutes: int
    allow_guests: bool = False
    created_at: datetime
    updated_at: datetime
    # 접근권한 관련 필드
    visibility_level: Optional[VisibilityLevel] = None
    is_shared: bool = False  # 공유된 일정인지 (다른 사용자의 일정)

    def to_timezone(self, tz: timezone | str | None) -> "MeetingRead":
        """
        UTC naive datetime 필드를 지정된 타임존의 aware datetime으로 변환
        
        :param tz: 타임존 (timezone 객체, 문자열, 또는 None)
        :return: 타임존이 변환된 새로운 MeetingRead 인스턴스
        """
        if tz is None:
            return self

        # datetime 필드만 타임존 변환
        update_data = {}
        for field_name in ["created_at", "updated_at"]:
            value = getattr(self, field_name, None)
            if value is not None and isinstance(value, datetime):
                update_data[field_name] = convert_utc_naive_to_timezone(value, tz)

        # model_construct 사용 (변환된 aware datetime이 validator를 통과하지 못하므로)
        data = self.model_dump()
        data.update(update_data)
        return MeetingRead.model_construct(**data)


DISPLAY_NAME_MAX_LENGTH = 50


class ParticipantCreate(CustomModel):
    """참여자 생성 DTO"""
    display_name: str  # 표시 이름 (닉네임)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, v: str) -> str:
        """앞뒤 공백을 뺀 1–50자, 제어 문자 불가"""
        v = v.strip()
        if not 1 <= len(v) <= DISPLAY_NAME_MAX_LENGTH:
            raise ValueError(f"display_name must be 1-{DISPLAY_NAME_MAX_LENGTH} characters after trimming")
        if any(unicodedata.category(ch) == "Cc" for ch in v):
            raise ValueError("display_name must not contain control characters")
        return v


class ParticipantRead(CustomModel):
    """참여자 조회 DTO"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    meeting_id: UUID
    user_id: Optional[str] = None
    display_name: str
    created_at: datetime

    def to_timezone(self, tz: timezone | str | None) -> "ParticipantRead":
        """
        UTC naive datetime 필드를 지정된 타임존의 aware datetime으로 변환
        
        :param tz: 타임존 (timezone 객체, 문자열, 또는 None)
        :return: 타임존이 변환된 새로운 ParticipantRead 인스턴스
        """
        if tz is None:
            return self

        # datetime 필드만 타임존 변환
        update_data = {}
        if self.created_at is not None:
            update_data["created_at"] = convert_utc_naive_to_timezone(self.created_at, tz)

        # model_construct 사용
        data = self.model_dump()
        data.update(update_data)
        return ParticipantRead.model_construct(**data)


class TimeSlotCreate(CustomModel):
    """가능 시간 생성 DTO: 반열린 구간 [start_time, end_time). 시간대가 없는 값은 UTC로 읽는다"""
    start_time: datetime
    end_time: datetime

    @field_validator("start_time", "end_time")
    @classmethod
    def ensure_utc_naive_datetime(cls, v):
        """datetime 필드를 UTC naive로 변환"""
        return ensure_utc_naive(v)

    @field_validator("end_time")
    @classmethod
    def validate_time_range(cls, v, info):
        validate_time_order(info.data.get("start_time"), v)
        return v


class TimeSlotRead(CustomModel):
    """시간 슬롯 조회 DTO"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    participant_id: UUID
    start_time: datetime
    end_time: datetime

    def to_timezone(self, tz: timezone | str | None) -> "TimeSlotRead":
        """UTC naive datetime 필드를 지정된 타임존의 aware datetime으로 변환"""
        if tz is None:
            return self
        data = self.model_dump()
        data["start_time"] = convert_utc_naive_to_timezone(self.start_time, tz)
        data["end_time"] = convert_utc_naive_to_timezone(self.end_time, tz)
        return TimeSlotRead.model_construct(**data)


class AvailabilityRead(CustomModel):
    """참여자별 가능 시간 조회 DTO"""
    participant: ParticipantRead
    time_slots: List[TimeSlotRead]

    def to_timezone(self, tz: timezone | str | None) -> "AvailabilityRead":
        if tz is None:
            return self
        return AvailabilityRead.model_construct(
            participant=self.participant.to_timezone(tz),
            time_slots=[slot.to_timezone(tz) for slot in self.time_slots],
        )


class AvailabilityCell(CustomModel):
    """결과 그리드의 칸 [start_time, end_time)과 그 칸을 모두 덮는 가능 시간을 가진 참여자 수"""
    start_time: datetime
    end_time: datetime
    count: int

    def to_timezone(self, tz: timezone | str | None) -> "AvailabilityCell":
        if tz is None:
            return self
        return AvailabilityCell.model_construct(
            start_time=convert_utc_naive_to_timezone(self.start_time, tz),
            end_time=convert_utc_naive_to_timezone(self.end_time, tz),
            count=self.count,
        )


class MeetingResultRead(CustomModel):
    """공통 가능 시간 분석 결과 DTO"""
    meeting: MeetingRead
    availability_grid: List[AvailabilityCell]  # 시작 시각 순

    def to_timezone(self, tz: timezone | str | None) -> "MeetingResultRead":
        if tz is None:
            return self
        return MeetingResultRead.model_construct(
            meeting=self.meeting.to_timezone(tz),
            availability_grid=[cell.to_timezone(tz) for cell in self.availability_grid],
        )
