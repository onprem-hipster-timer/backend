"""
Meeting Domain DTO (Data Transfer Objects)

일정 조율 관련 데이터 전송 객체
"""
import unicodedata
from bisect import bisect_left
from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated, Optional, List
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil.relativedelta import relativedelta
from pydantic import AfterValidator, ConfigDict, ValidationInfo, field_validator, model_validator
from pydantic.experimental.missing_sentinel import MISSING

from app.core.base_model import CustomModel
from app.domain.dateutil.service import convert_utc_naive_to_timezone, ensure_utc_naive
from app.models.meeting import MeetingMode, TimeSlotKind
from app.models.visibility import VisibilityLevel
from app.utils.validators import validate_time_order


TITLE_MAX_LENGTH = 200
DESCRIPTION_MAX_LENGTH = 2000
MAX_PERIOD = relativedelta(months=3)
TIME_SLOT_MINUTES_MIN = 5
TIME_SLOT_MINUTES_MAX = 1440
HOURLY_MAX_DAYS = 7
WEEKLY_DAYS = 7
# 방식의 규칙(MeetingCreate.validate_mode)이 읽는 필드
MODE_RULE_FIELDS = ("mode", "start_date", "end_date", "excluded_dates", "start_time", "end_time")


def daily_range(start_time: time, end_time: time) -> timedelta:
    """하루 범위 [start_time, end_time). end_time 00:00은 다음 날 00:00(하루의 끝)이다"""
    end = datetime.combine(date.min + timedelta(days=1 if end_time == time(0) else 0), end_time)
    return end - datetime.combine(date.min, start_time)


def meeting_dates(start_date: date, end_date: date, excluded_dates: List[date]) -> List[date]:
    """미팅의 날짜: start_date~end_date에서 excluded_dates를 뺀 날 (순서대로)"""
    days = (start_date + timedelta(days=offset) for offset in range((end_date - start_date).days + 1))
    excluded = set(excluded_dates)
    return [day for day in days if day not in excluded]


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


def _validate_excluded_dates(v: list[date]) -> list[date]:
    """겹치지 않는 날짜, 정렬해 돌려준다 (기간 안쪽인지는 MeetingCreate.validate_shape)"""
    if len(set(v)) != len(v):
        raise ValueError("excluded_dates must not contain duplicates")
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
    방식의 규칙은 그때 MODE_RULE_FIELDS 중 하나라도 저장된 값과 달라질 때만 본다 (검증 context의 skip_mode_rules).
    """
    title: str
    description: Optional[str] = None
    start_date: date
    end_date: date
    excluded_dates: List[date] = []  # 기간에서 빼는 날짜. 첫날·마지막 날이 아닌 기간 안쪽 날짜만
    timezone: str  # 날짜·시간을 해석하는 IANA 시간대
    mode: MeetingMode  # 답하는 방식
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

    @field_validator("excluded_dates")
    @classmethod
    def validate_excluded_dates(cls, v):
        return _validate_excluded_dates(v)

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
        """기간은 start_date + 3개월(같은 날, 없으면 그 달 말일)까지, 제외 날짜는 기간 안쪽, 시간 단위는 하루 범위 이하"""
        if self.end_date > self.start_date + MAX_PERIOD:
            raise ValueError("end_date must be no later than 3 months after start_date")
        if not all(self.start_date < day < self.end_date for day in self.excluded_dates):
            raise ValueError("excluded_dates must be after start_date and before end_date")
        if self.time_slot_minutes * 60 > daily_range(self.start_time, self.end_time).total_seconds():
            raise ValueError("time_slot_minutes must not exceed end_time - start_time")
        return self

    @model_validator(mode="after")
    def validate_mode(self, info: ValidationInfo):
        """hourly는 7일 이하. daily는 하루 전체(00:00–00:00). weekly는 정확히 7일, 제외 날짜 없음, 하루 전체"""
        if (info.context or {}).get("skip_mode_rules"):
            return self
        days = (self.end_date - self.start_date).days + 1
        whole_day = self.start_time == time(0) and self.end_time == time(0)
        if self.mode == MeetingMode.HOURLY and days > HOURLY_MAX_DAYS:
            raise ValueError(f"hourly meetings must span at most {HOURLY_MAX_DAYS} days")
        if self.mode == MeetingMode.DAILY and not whole_day:
            raise ValueError("daily meetings must cover the whole day (start_time and end_time 00:00)")
        if self.mode == MeetingMode.WEEKLY:
            if days != WEEKLY_DAYS:
                raise ValueError(f"weekly meetings must span exactly {WEEKLY_DAYS} days")
            if self.excluded_dates:
                raise ValueError("weekly meetings must not have excluded_dates")
            if not whole_day:
                raise ValueError("weekly meetings must cover the whole day (start_time and end_time 00:00)")
        return self


class MeetingUpdate(CustomModel):
    """일정 조율 업데이트 DTO"""
    title: str | None = MISSING
    description: str | None = MISSING
    start_date: date | None = MISSING
    end_date: date | None = MISSING
    excluded_dates: list[date] = MISSING
    timezone: str = MISSING
    mode: MeetingMode = MISSING
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

    @field_validator("excluded_dates")
    @classmethod
    def validate_excluded_dates(cls, v):
        return _validate_excluded_dates(v)

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
    owner_id: Optional[str] = None  # 소유자 sub. 로그인하지 않은 방문자와 게스트에게는 null
    title: str
    description: Optional[str] = None
    start_date: date
    end_date: date
    excluded_dates: List[date]
    timezone: str
    mode: MeetingMode
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
    is_owner: bool = False  # 미팅 소유자의 참여자인지
    is_guest: bool = False  # 게스트 참여자인지

    @classmethod
    def from_participant(cls, participant, owner_id: str) -> "ParticipantRead":
        """참여자 행과 미팅 소유자의 sub로 만든다 (is_owner, is_guest를 채운다)"""
        participant_read = cls.model_validate(participant)
        participant_read.is_owner = participant.user_id is not None and participant.user_id == owner_id
        participant_read.is_guest = participant.guest_id is not None
        return participant_read

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
    kind: TimeSlotKind = TimeSlotKind.AVAILABLE

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


def merge_intervals(intervals: List[tuple[datetime, datetime]]) -> List[tuple[datetime, datetime]]:
    """겹치거나 맞닿은 반열린 구간을 합친다 (시작 순)"""
    merged: List[tuple[datetime, datetime]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _validate_kinds_do_not_overlap(slots: List[TimeSlotCreate]) -> List[TimeSlotCreate]:
    """한 참여자의 available 구간과 unavailable 구간은 겹칠 수 없다 (맞닿는 것은 된다)"""
    available = merge_intervals([
        (slot.start_time, slot.end_time) for slot in slots if slot.kind == TimeSlotKind.AVAILABLE
    ])
    starts = [start for start, _ in available]
    for slot in slots:
        if slot.kind != TimeSlotKind.UNAVAILABLE:
            continue
        # unavailable 구간의 끝보다 먼저 시작하는 마지막 available 구간만 보면 된다
        i = bisect_left(starts, slot.end_time) - 1
        if i >= 0 and available[i][1] > slot.start_time:
            raise ValueError("available and unavailable time slots must not overlap")
    return slots


# PUT /availability의 요청 본문: 참여자의 가능 시간 전체
TimeSlotList = Annotated[List[TimeSlotCreate], AfterValidator(_validate_kinds_do_not_overlap)]


class TimeSlotRead(CustomModel):
    """시간 슬롯 조회 DTO"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    participant_id: UUID
    start_time: datetime
    end_time: datetime
    kind: TimeSlotKind

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
    """결과 그리드의 칸 [start_time, end_time)과 그 칸을 모두 덮는 available·unavailable 구간을 가진 참여자 수"""
    start_time: datetime
    end_time: datetime
    count: int
    unavailable_count: int

    def to_timezone(self, tz: timezone | str | None) -> "AvailabilityCell":
        if tz is None:
            return self
        return AvailabilityCell.model_construct(
            start_time=convert_utc_naive_to_timezone(self.start_time, tz),
            end_time=convert_utc_naive_to_timezone(self.end_time, tz),
            count=self.count,
            unavailable_count=self.unavailable_count,
        )


class MeetingResultRead(CustomModel):
    """공통 가능 시간 분석 결과 DTO"""
    meeting: MeetingRead
    participant_count: int  # 참여자 수 (휴면 회원 제외, 가능 시간을 넣지 않은 참여자 포함)
    availability_grid: List[AvailabilityCell]  # 시작 시각 순

    def to_timezone(self, tz: timezone | str | None) -> "MeetingResultRead":
        if tz is None:
            return self
        return MeetingResultRead.model_construct(
            meeting=self.meeting.to_timezone(tz),
            participant_count=self.participant_count,
            availability_grid=[cell.to_timezone(tz) for cell in self.availability_grid],
        )
