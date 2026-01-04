"""
Timer Domain DTO (Data Transfer Objects)

아키텍처 원칙:
- Domain이 자신의 DTO를 정의
- REST API와 GraphQL 모두에서 사용
- Pydantic을 사용한 데이터 검증
"""
from datetime import datetime, timezone
from typing import Optional, List, TYPE_CHECKING
from uuid import UUID

from pydantic import ConfigDict, field_validator

from app.core.base_model import CustomModel
from app.core.constants import TagIncludeMode
from app.domain.dateutil.service import convert_utc_naive_to_timezone, ensure_utc_naive
from app.domain.schedule.schema.dto import ScheduleRead

if TYPE_CHECKING:
    from app.domain.tag.schema.dto import TagRead


class TimerCreate(CustomModel):
    """타이머 생성 DTO"""
    schedule_id: UUID
    title: Optional[str] = None
    description: Optional[str] = None
    allocated_duration: int  # 할당 시간 (초 단위)
    tag_ids: Optional[List[UUID]] = None  # 태그 ID 리스트

    @field_validator("allocated_duration")
    @classmethod
    def validate_allocated_duration(cls, v):
        """allocated_duration 검증"""
        if v <= 0:
            raise ValueError("allocated_duration must be positive")
        return v


class TimerRead(CustomModel):
    """타이머 조회 DTO"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    schedule_id: UUID
    title: Optional[str] = None
    description: Optional[str] = None
    allocated_duration: int
    elapsed_time: int
    status: str  # TimerStatus enum 값
    started_at: Optional[datetime] = None
    paused_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    # 일정 정보 포함 (선택적)
    schedule: Optional[ScheduleRead] = None

    # 태그 목록
    tags: List["TagRead"] = []

    @field_validator("started_at", "paused_at", "ended_at", "created_at", "updated_at")
    @classmethod
    def ensure_utc_naive_datetime(cls, v):
        """datetime 필드를 UTC naive로 변환"""
        return ensure_utc_naive(v) if v is not None else None

    @classmethod
    def from_model(
            cls,
            timer: "TimerSession",
            *,
            include_schedule: bool = False,
            schedule: Optional[ScheduleRead] = None,
            tag_include_mode: TagIncludeMode = TagIncludeMode.NONE,
            tags: Optional[List["TagRead"]] = None,
    ) -> "TimerRead":
        """
        TimerSession 모델에서 TimerRead DTO를 안전하게 생성
        
        관계 필드(schedule, tags)를 제외하고 변환하여 의도치 않은 DB 쿼리 방지
        include_schedule=True일 때만 schedule 정보를 포함
        tag_include_mode에 따라 tags 정보를 포함
        
        :param timer: TimerSession 모델 인스턴스
        :param include_schedule: Schedule 정보 포함 여부
        :param schedule: ScheduleRead 인스턴스 (include_schedule=True일 때만 사용)
        :param tag_include_mode: 태그 포함 모드 (NONE, TIMER_ONLY, INHERIT_FROM_SCHEDULE)
        :param tags: TagRead 리스트 (tag_include_mode가 NONE이 아닐 때 사용)
        :return: TimerRead DTO 인스턴스
        """
        # schedule, tags 관계를 제외하여 안전하게 변환 (의도치 않은 lazy load 방지)
        timer_data = timer.model_dump(exclude={"schedule", "tags"})
        timer_read = cls.model_validate(timer_data)

        # schedule 필드 명시적으로 설정
        timer_read.schedule = schedule if include_schedule else None

        # tags 필드 명시적으로 설정
        if tag_include_mode == TagIncludeMode.NONE:
            timer_read.tags = []
        else:
            timer_read.tags = tags if tags is not None else []

        return timer_read

    def to_timezone(self, tz: timezone | str | None, validate: bool = True) -> "TimerRead":
        """
        UTC naive datetime 필드를 지정된 타임존의 aware datetime으로 변환
        
        :param tz: 타임존 (timezone 객체, 문자열, 또는 None)
        :param validate: datetime 필드를 UTC naive로 검증할지 여부 (기본값: True)
                         False로 설정 시 self가 이미 검증되었다고 가정합니다.
        :return: 타임존이 변환된 새로운 TimerRead 인스턴스
        """
        if tz is None:
            return self

        # datetime 필드만 타임존 변환
        update_data = {}
        for field_name in ["started_at", "paused_at", "ended_at", "created_at", "updated_at"]:
            value = getattr(self, field_name, None)
            if value is not None and isinstance(value, datetime):
                if validate:
                    # validate=True: UTC naive로 보장 (self가 검증되지 않았을 수도 있음)
                    naive_value = ensure_utc_naive(value)
                    update_data[field_name] = convert_utc_naive_to_timezone(naive_value, tz)
                else:
                    # validate=False: 이미 검증된 것으로 가정
                    update_data[field_name] = convert_utc_naive_to_timezone(value, tz)

        # schedule 필드 처리
        schedule_value = getattr(self, "schedule", None)
        if schedule_value is not None:
            if isinstance(schedule_value, ScheduleRead):
                # ScheduleRead 인스턴스는 validate=False (이미 검증된 것으로 가정)
                update_data["schedule"] = schedule_value.to_timezone(tz, validate=False)
            else:
                # dict인 경우 ScheduleRead로 변환 후 변환 (model_construct 사용하여 validator 우회)
                schedule_read = ScheduleRead.model_construct(**schedule_value)
                update_data["schedule"] = schedule_read.to_timezone(tz, validate=False)

        # model_construct 사용 (변환된 aware datetime이 validator를 통과하지 못하므로)
        data = self.model_dump()
        data.update(update_data)
        return TimerRead.model_construct(**data)


class TimerUpdate(CustomModel):
    """타이머 업데이트 DTO"""
    title: Optional[str] = None
    description: Optional[str] = None
    tag_ids: Optional[List[UUID]] = None  # 태그 ID 리스트


# Forward reference 해결 (TagRead 임포트)

TimerRead.model_rebuild()
