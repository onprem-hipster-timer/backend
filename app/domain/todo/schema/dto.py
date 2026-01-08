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
from app.domain.tag.schema.dto import TagRead


class TodoCreate(CustomModel):
    """Todo 생성 DTO"""
    title: str
    description: Optional[str] = None
    tag_ids: Optional[List[UUID]] = None
    # 마감 시간 (선택) - 없으면 917초로 설정됨
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


class TodoRead(CustomModel):
    """Todo 조회 DTO"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: Optional[str] = None
    is_todo: bool = True  # 항상 True
    start_time: datetime  # 마감 시간이 있으면 실제 시간, 없으면 917초
    end_time: datetime
    created_at: datetime
    tags: List[TagRead] = []

    @classmethod
    def from_schedule(cls, schedule, tags: Optional[List[TagRead]] = None) -> "TodoRead":
        """
        Schedule 모델에서 TodoRead 생성
        
        :param schedule: Schedule 모델 인스턴스
        :param tags: 태그 목록 (선택)
        :return: TodoRead 인스턴스
        """
        return cls(
            id=schedule.id,
            title=schedule.title,
            description=schedule.description,
            is_todo=schedule.is_todo,
            start_time=schedule.start_time,
            end_time=schedule.end_time,
            created_at=schedule.created_at,
            tags=tags or [],
        )


class TodoUpdate(CustomModel):
    """Todo 업데이트 DTO
    
    Todo를 일정으로 변환하려면 is_todo=false와 함께 
    start_time/end_time을 반드시 지정해야 합니다.
    """
    title: Optional[str] = None
    description: Optional[str] = None
    tag_ids: Optional[List[UUID]] = None
    # 마감 시간 변경 가능
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    is_todo: Optional[bool] = None  # Todo <-> 일정 변환용


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

