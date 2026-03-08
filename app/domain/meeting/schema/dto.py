"""
Meeting Domain DTO (Data Transfer Objects)

일정 조율 관련 데이터 전송 객체
"""
from datetime import date, datetime, time, timezone
from typing import Optional, List
from uuid import UUID

from pydantic import ConfigDict, field_validator
from pydantic.experimental.missing_sentinel import MISSING

from app.core.base_model import CustomModel
from app.domain.dateutil.service import convert_utc_naive_to_timezone
from app.models.visibility import VisibilityLevel


class MeetingCreate(CustomModel):
    """일정 조율 생성 DTO"""
    title: str
    description: Optional[str] = None
    start_date: date
    end_date: date
    available_days: List[int]  # 요일 리스트 (0-6, 0=월요일)
    start_time: time  # 하루 시작 시간
    end_time: time  # 하루 종료 시간
    time_slot_minutes: int = 30  # 시간 선택 단위 (분)

    @field_validator("available_days")
    @classmethod
    def validate_available_days(cls, v):
        """요일 리스트 검증"""
        if not isinstance(v, list):
            raise ValueError("available_days must be a list")
        if not all(isinstance(d, int) and 0 <= d <= 6 for d in v):
            raise ValueError("available_days must contain integers 0-6")
        if len(set(v)) != len(v):
            raise ValueError("available_days must not contain duplicates")
        return sorted(v)

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
        if start_time and v <= start_time:
            raise ValueError("end_time must be > start_time")
        return v

    @field_validator("time_slot_minutes")
    @classmethod
    def validate_time_slot_minutes(cls, v):
        """시간 슬롯 단위 검증"""
        if v <= 0:
            raise ValueError("time_slot_minutes must be > 0")
        return v


class MeetingUpdate(CustomModel):
    """일정 조율 업데이트 DTO"""
    title: str | None = MISSING
    description: str | None = MISSING
    start_date: date | None = MISSING
    end_date: date | None = MISSING
    available_days: list[int] | None = MISSING
    start_time: time | None = MISSING
    end_time: time | None = MISSING
    time_slot_minutes: int | None = MISSING

    @field_validator("available_days")
    @classmethod
    def validate_available_days(cls, v):
        """요일 리스트 검증"""
        if v is not None:
            if not isinstance(v, list):
                raise ValueError("available_days must be a list")
            if not all(isinstance(d, int) and 0 <= d <= 6 for d in v):
                raise ValueError("available_days must contain integers 0-6")
            if len(set(v)) != len(v):
                raise ValueError("available_days must not contain duplicates")
            return sorted(v)
        return v

    @field_validator("time_slot_minutes")
    @classmethod
    def validate_time_slot_minutes(cls, v):
        """시간 슬롯 단위 검증"""
        if v is not None and v <= 0:
            raise ValueError("time_slot_minutes must be > 0")
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
    available_days: List[int]
    start_time: time
    end_time: time
    time_slot_minutes: int
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


class ParticipantCreate(CustomModel):
    """참여자 생성 DTO"""
    display_name: str  # 표시 이름 (닉네임)


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
    """시간 슬롯 생성 DTO"""
    slot_date: date
    start_time: time
    end_time: time

    @field_validator("end_time")
    @classmethod
    def validate_time_range(cls, v, info):
        """시간 범위 검증"""
        start_time = info.data.get("start_time")
        if start_time and v <= start_time:
            raise ValueError("end_time must be > start_time")
        return v


class TimeSlotRead(CustomModel):
    """시간 슬롯 조회 DTO"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    participant_id: UUID
    slot_date: date
    start_time: time
    end_time: time


class AvailabilityRead(CustomModel):
    """참여자별 가능 시간 조회 DTO"""
    participant: ParticipantRead
    time_slots: List[TimeSlotRead]


class AvailabilityTimeSlot(CustomModel):
    """시간 슬롯별 가용 인원 DTO"""
    time: str   # "HH:MM" 형식
    count: int  # 해당 시간대에 가능한 참여자 수


class AvailabilityDateGroup(CustomModel):
    """날짜별 가용 시간 그룹 DTO"""
    date: str                           # "YYYY-MM-DD" 형식
    slots: List[AvailabilityTimeSlot]


class MeetingResultRead(CustomModel):
    """공통 가능 시간 분석 결과 DTO"""
    meeting: MeetingRead
    availability_grid: List[AvailabilityDateGroup]
