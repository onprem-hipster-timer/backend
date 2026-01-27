"""
Todo Domain DTO (Data Transfer Objects)

아키텍처 원칙:
- Domain이 자신의 DTO를 정의
- REST API에서 사용
- Pydantic을 사용한 데이터 검증
"""
from datetime import datetime
from enum import Enum
from typing import Optional, List
from uuid import UUID

from pydantic import ConfigDict

from app.core.base_model import CustomModel
from app.domain.schedule.schema.dto import ScheduleRead, VisibilitySettings
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
    visibility: Optional[VisibilitySettings] = None  # 가시성 설정


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
    # 가시성 관련 필드
    owner_id: Optional[str] = None  # 소유자 ID (공유된 Todo 조회 시)
    visibility_level: Optional[VisibilityLevel] = None  # 가시성 레벨
    is_shared: bool = False  # 공유된 Todo인지


class TodoUpdate(CustomModel):
    """Todo 업데이트 DTO"""
    title: Optional[str] = None
    description: Optional[str] = None
    tag_group_id: Optional[UUID] = None  # 소속 그룹 변경
    tag_ids: Optional[List[UUID]] = None  # 태그는 선택
    deadline: Optional[datetime] = None  # 마감기간 변경
    parent_id: Optional[UUID] = None  # 부모 Todo 변경
    status: Optional[TodoStatus] = None  # 상태 변경
    visibility: Optional[VisibilitySettings] = None  # 가시성 설정


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
