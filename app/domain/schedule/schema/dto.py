"""
Schedule Domain DTO (Data Transfer Objects)

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
from app.domain.dateutil.service import convert_utc_naive_to_timezone, ensure_utc_naive
from app.domain.schedule.enums import ScheduleState
from app.domain.tag.schema.dto import TagRead
from app.models.visibility import VisibilityLevel
from app.utils.validators import validate_time_order

if TYPE_CHECKING:
    from app.domain.tag.schema.dto import TagRead


class CreateTodoOptions(CustomModel):
    """Schedule 생성 시 함께 생성할 Todo 옵션"""
    tag_group_id: UUID  # Todo가 속할 그룹 (필수)


class VisibilitySettings(CustomModel):
    """가시성 설정 DTO"""
    level: VisibilityLevel = VisibilityLevel.PRIVATE
    allowed_user_ids: Optional[List[str]] = None  # SELECTED_FRIENDS 레벨에서만 사용


class ScheduleCreate(CustomModel):
    """일정 생성 DTO"""
    title: str
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime
    recurrence_rule: Optional[str] = None  # RRULE 형식: "FREQ=WEEKLY;BYDAY=MO"
    recurrence_end: Optional[datetime] = None  # 반복 종료일
    tag_ids: Optional[List[UUID]] = None  # 태그 ID 리스트
    tag_group_id: Optional[UUID] = None  # Todo 그룹 직접 연결 (레거시)
    source_todo_id: Optional[UUID] = None  # Todo에서 생성된 Schedule 추적
    state: Optional[ScheduleState] = ScheduleState.PLANNED  # 상태 (기본값: PLANNED)
    create_todo_options: Optional[CreateTodoOptions] = None  # Schedule과 함께 Todo 생성 옵션
    visibility: Optional[VisibilitySettings] = None  # 가시성 설정

    @field_validator("start_time", "end_time", "recurrence_end")
    @classmethod
    def ensure_utc_naive_datetime(cls, v):
        """datetime 필드를 UTC naive로 변환"""
        return ensure_utc_naive(v) if v is not None else None

    @field_validator("end_time")
    def validate_time(cls, end_time, info):
        validate_time_order(info.data.get("start_time"), end_time)
        return end_time


class ScheduleRead(CustomModel):
    """일정 조회 DTO"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime
    recurrence_rule: Optional[str] = None
    recurrence_end: Optional[datetime] = None
    parent_id: Optional[UUID] = None  # 원본 일정 ID (가상 인스턴스인 경우)
    tag_group_id: Optional[UUID] = None  # Todo 그룹 직접 연결 (레거시)
    source_todo_id: Optional[UUID] = None  # Todo에서 생성된 Schedule 추적
    state: ScheduleState  # 상태
    created_at: datetime
    tags: List["TagRead"] = []  # 태그 목록
    # 가시성 관련 필드
    owner_id: Optional[str] = None  # 소유자 ID (공유된 일정 조회 시)
    visibility_level: Optional[VisibilityLevel] = None  # 가시성 레벨
    is_shared: bool = False  # 공유된 일정인지 (다른 사용자의 일정)

    def to_timezone(self, tz: timezone | str | None, validate: bool = True) -> "ScheduleRead":
        """
        UTC naive datetime 필드를 지정된 타임존의 aware datetime으로 변환
        
        :param tz: 타임존 (timezone 객체, 문자열, 또는 None)
        :param validate: datetime 필드를 UTC naive로 검증할지 여부 (기본값: True)
                         False로 설정 시 self가 이미 검증되었다고 가정합니다.
        :return: 타임존이 변환된 새로운 ScheduleRead 인스턴스
        """
        if tz is None:
            return self

        # datetime 필드만 타임존 변환
        update_data = {}
        for field_name in ["start_time", "end_time", "recurrence_end", "created_at"]:
            value = getattr(self, field_name, None)
            if value is not None and isinstance(value, datetime):
                if validate:
                    # validate=True: UTC naive로 보장 (self가 검증되지 않았을 수도 있음)
                    naive_value = ensure_utc_naive(value)
                    update_data[field_name] = convert_utc_naive_to_timezone(naive_value, tz)
                else:
                    # validate=False: 이미 검증된 것으로 가정
                    update_data[field_name] = convert_utc_naive_to_timezone(value, tz)

        # model_construct 사용 (변환된 aware datetime이 validator를 통과하지 못하므로)
        data = self.model_dump()
        data.update(update_data)
        return ScheduleRead.model_construct(**data)


class ScheduleUpdate(CustomModel):
    """일정 업데이트 DTO"""
    title: Optional[str] = None
    description: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    recurrence_rule: Optional[str] = None  # RRULE 형식: "FREQ=WEEKLY;BYDAY=MO"
    recurrence_end: Optional[datetime] = None  # 반복 종료일
    tag_ids: Optional[List[UUID]] = None  # 태그 ID 리스트
    tag_group_id: Optional[UUID] = None  # Todo 그룹 직접 연결 (레거시)
    source_todo_id: Optional[UUID] = None  # Todo에서 생성된 Schedule 추적
    state: Optional[ScheduleState] = None  # 상태
    visibility: Optional[VisibilitySettings] = None  # 가시성 설정

    @field_validator("start_time", "end_time", "recurrence_end")
    @classmethod
    def ensure_utc_naive_datetime(cls, v):
        """datetime 필드를 UTC naive로 변환"""
        return ensure_utc_naive(v) if v is not None else None

    @field_validator("end_time")
    def validate_time(cls, end_time, info):
        validate_time_order(info.data.get("start_time"), end_time)
        return end_time


# Forward reference 해결 (TagRead 임포트)

ScheduleRead.model_rebuild()
