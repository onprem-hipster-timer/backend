"""
Todo Domain DTO (Data Transfer Objects)

아키텍처 원칙:
- Domain이 자신의 DTO를 정의
- REST API에서 사용
- Pydantic을 사용한 데이터 검증
"""
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import ConfigDict

from app.core.base_model import CustomModel
from app.domain.schedule.schema.dto import ScheduleRead
from app.domain.tag.schema.dto import TagRead
from app.domain.todo.enums import TodoStatus


class TodoCreate(CustomModel):
    """Todo 생성 DTO"""
    title: str
    description: Optional[str] = None
    tag_group_id: UUID  # Todo가 속할 그룹 (필수)
    tag_ids: Optional[List[UUID]] = None  # 태그는 선택
    deadline: Optional[datetime] = None  # 마감기간 (선택)
    parent_id: Optional[UUID] = None  # 부모 Todo ID (트리 구조)
    status: Optional[TodoStatus] = TodoStatus.UNSCHEDULED  # 상태 (기본값: UNSCHEDULED)


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


class TodoUpdate(CustomModel):
    """Todo 업데이트 DTO"""
    title: Optional[str] = None
    description: Optional[str] = None
    tag_group_id: Optional[UUID] = None  # 소속 그룹 변경
    tag_ids: Optional[List[UUID]] = None  # 태그는 선택
    deadline: Optional[datetime] = None  # 마감기간 변경
    parent_id: Optional[UUID] = None  # 부모 Todo 변경
    status: Optional[TodoStatus] = None  # 상태 변경


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

