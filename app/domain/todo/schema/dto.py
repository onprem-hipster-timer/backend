"""
Todo Domain DTO (Data Transfer Objects)

아키텍처 원칙:
- Domain이 자신의 DTO를 정의
- REST API에서 사용
- Pydantic을 사용한 데이터 검증
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List
from uuid import UUID

from pydantic import ConfigDict, field_validator
from pydantic.experimental.missing_sentinel import MISSING

from app.core.base_model import CustomModel
from app.domain.dateutil.service import convert_utc_naive_to_timezone, ensure_utc_naive
from app.domain.schedule.schema.dto import ScheduleRead
from app.domain.tag.schema.dto import TagRead
from app.domain.todo.enums import TodoStatus
from app.models.visibility import VisibilityLevel


class TodoIncludeReason(str, Enum):
    """Todo가 응답에 포함된 사유"""
    MATCH = "MATCH"  # 필터 조건에 직접 매칭됨
    ANCESTOR = "ANCESTOR"  # 매칭된 Todo의 조상이라 포함됨


class TodoCreate(CustomModel):
    """Todo 생성 DTO"""
    title: str
    description: Optional[str] = None
    tag_group_id: UUID  # Todo가 속할 그룹 (필수)
    tag_ids: Optional[List[UUID]] = None  # 태그는 선택
    deadline: Optional[datetime] = None  # 마감기간 (선택)
    parent_id: Optional[UUID] = None  # 부모 Todo ID (트리 구조)
    status: Optional[TodoStatus] = TodoStatus.UNSCHEDULED  # 상태 (기본값: UNSCHEDULED)

    @field_validator("deadline")
    @classmethod
    def ensure_utc_naive_datetime(cls, v):
        """deadline을 UTC naive로 변환

        해외 출장 등으로 클라이언트가 자기 타임존이 붙은 aware datetime을 보낼 수 있다.
        DB는 naive UTC(TIMESTAMP WITHOUT TIME ZONE)로 저장하므로,
        aware datetime은 UTC로 변환 후 naive로 저장한다. (#41 동일 버그 클래스 방지)
        """
        return ensure_utc_naive(v) if v is not None else None


class TodoRead(CustomModel):
    """Todo 조회 DTO"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: Optional[str] = None
    deadline: Optional[datetime] = None  # 마감기간
    tag_group_id: UUID  # 소속 그룹 ID (필수)
    parent_id: Optional[UUID] = None  # 부모 Todo ID
    status: TodoStatus  # 상태
    created_at: datetime
    tags: List[TagRead] = []
    schedules: List[ScheduleRead] = []  # 연관된 Schedule 목록
    include_reason: TodoIncludeReason = TodoIncludeReason.MATCH  # 포함 사유 (필터 매칭/조상)
    # 접근권한 관련 필드
    owner_id: Optional[str] = None  # 소유자 ID (공유된 Todo 조회 시)
    visibility_level: Optional[VisibilityLevel] = None  # 접근권한 레벨
    is_shared: bool = False  # 공유된 Todo인지

    def to_timezone(self, tz: timezone | str | None, validate: bool = True) -> "TodoRead":
        """
        UTC naive datetime 필드를 지정된 타임존의 aware datetime으로 변환

        DB에는 UTC naive로 저장되므로, 클라이언트가 요청한 타임존으로 변환하여 응답한다.
        연관된 Schedule(schedules)도 동일 타임존으로 변환한다.

        :param tz: 타임존 (timezone 객체, 문자열, 또는 None)
        :param validate: datetime 필드를 UTC naive로 검증할지 여부 (기본값: True)
                         False로 설정 시 self가 이미 검증되었다고 가정합니다.
        :return: 타임존이 변환된 새로운 TodoRead 인스턴스
        """
        if tz is None:
            return self

        # datetime 필드만 타임존 변환
        update_data = {}
        for field_name in ["deadline", "created_at"]:
            value = getattr(self, field_name, None)
            if value is not None and isinstance(value, datetime):
                if validate:
                    # validate=True: UTC naive로 보장 (self가 검증되지 않았을 수도 있음)
                    naive_value = ensure_utc_naive(value)
                    update_data[field_name] = convert_utc_naive_to_timezone(naive_value, tz)
                else:
                    # validate=False: 이미 검증된 것으로 가정
                    update_data[field_name] = convert_utc_naive_to_timezone(value, tz)

        # 연관 Schedule도 동일 타임존으로 변환 (이미 UTC naive로 검증된 것으로 가정)
        if self.schedules:
            update_data["schedules"] = [
                schedule.to_timezone(tz, validate=False)
                if isinstance(schedule, ScheduleRead)
                else schedule
                for schedule in self.schedules
            ]

        # model_construct 사용 (변환된 aware datetime이 validator를 통과하지 못하므로)
        data = self.model_dump()
        data.update(update_data)
        return TodoRead.model_construct(**data)


class TodoUpdate(CustomModel):
    """Todo 업데이트 DTO"""
    title: str | None = MISSING
    description: str | None = MISSING
    tag_group_id: UUID | None = MISSING  # 소속 그룹 변경
    tag_ids: list[UUID] | None = MISSING  # 태그는 선택
    deadline: datetime | None = MISSING  # 마감기간 변경
    parent_id: UUID | None = MISSING  # 부모 Todo 변경
    status: TodoStatus | None = MISSING  # 상태 변경

    @field_validator("deadline")
    @classmethod
    def ensure_utc_naive_datetime(cls, v):
        """deadline을 UTC naive로 변환 (aware 입력 → UTC naive 저장, #41 방지)"""
        return ensure_utc_naive(v) if v is not None else None


class TagStat(CustomModel):
    """태그별 통계"""
    tag_id: UUID
    tag_name: str
    count: int


class TodoStats(CustomModel):
    """Todo 통계"""
    group_id: Optional[UUID] = None
    total_count: int
    by_tag: List[TagStat]
