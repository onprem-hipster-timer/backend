"""
Tag Domain GraphQL Types

아키텍처 원칙:
- Domain이 자신의 GraphQL 표현을 정의
- Strawberry는 Pydantic처럼 타입 정의 도구로 사용
"""
from datetime import datetime
from typing import List
from uuid import UUID

import strawberry

from app.models.tag import TagGroup as TagGroupModel, Tag as TagModel


@strawberry.type
class TagType:
    """GraphQL Tag 타입"""
    id: UUID
    name: str
    color: str
    description: str | None
    group_id: UUID
    created_at: datetime
    updated_at: datetime
    
    @classmethod
    def from_model(cls, tag: TagModel) -> "TagType":
        """ORM 모델을 GraphQL 타입으로 변환"""
        return cls(
            id=tag.id,
            name=tag.name,
            color=tag.color,
            description=tag.description,
            group_id=tag.group_id,
            created_at=tag.created_at,
            updated_at=tag.updated_at,
        )


@strawberry.type
class TagGroupType:
    """GraphQL TagGroup 타입"""
    id: UUID
    name: str
    color: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    tags: List[TagType]
    
    @classmethod
    def from_model(cls, group: TagGroupModel) -> "TagGroupType":
        """ORM 모델을 GraphQL 타입으로 변환"""
        return cls(
            id=group.id,
            name=group.name,
            color=group.color,
            description=group.description,
            created_at=group.created_at,
            updated_at=group.updated_at,
            tags=[TagType.from_model(tag) for tag in group.tags],
        )


@strawberry.input
class TagFilterInput:
    """태그 필터링 입력 타입"""
    tag_ids: List[UUID] | None = None  # 특정 태그들로 필터링 (AND 방식)
    group_ids: List[UUID] | None = None  # 특정 그룹의 모든 태그로 필터링




