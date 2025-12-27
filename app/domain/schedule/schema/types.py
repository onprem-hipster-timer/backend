"""
Schedule Domain GraphQL Types

아키텍처 원칙:
- Domain이 자신의 GraphQL 표현을 정의
- Strawberry는 Pydantic처럼 타입 정의 도구로 사용
- Domain의 외부 표현 중 하나
"""
from datetime import date, datetime
from typing import List
from uuid import UUID

import strawberry

from app.domain.schedule.model import Schedule


@strawberry.type
class Event:
    """
    GraphQL Event 타입 (Schedule의 GraphQL 표현)
    
    Domain이 자신의 GraphQL 표현을 정의합니다.
    """
    id: UUID
    title: str
    description: str | None
    start_at: datetime
    end_at: datetime
    created_at: datetime
    # 반복 일정 필드
    is_recurring: bool = False  # 반복 일정인지 여부
    parent_id: UUID | None = None  # 반복 일정의 원본 ID (가상 인스턴스인 경우)

    @classmethod
    def from_schedule(cls, schedule: Schedule) -> "Event":
        """
        Domain 모델을 GraphQL 타입으로 변환
        
        :param schedule: Schedule 도메인 모델
        :return: Event GraphQL 타입
        """
        return cls(
            id=schedule.id,
            title=schedule.title,
            description=schedule.description,
            start_at=schedule.start_time,
            end_at=schedule.end_time,
            created_at=schedule.created_at,
            is_recurring=schedule.recurrence_rule is not None or schedule.parent_id is not None,
            parent_id=schedule.parent_id,
        )


@strawberry.type
class Day:
    """
    GraphQL Day 타입 (특정 날짜와 해당 날짜의 이벤트들)
    
    캘린더 뷰를 위한 도메인 개념
    
    Bug Fix: 커스텀 __init__ 제거
    - Strawberry는 타입 어노테이션을 기반으로 자동으로 __init__ 생성
    - 커스텀 __init__은 Strawberry의 내부 메커니즘과 충돌 가능
    """
    date: date
    events: List[Event]


@strawberry.type
class Calendar:
    """
    GraphQL Calendar 타입 (날짜 범위와 해당 기간의 모든 날짜들)
    
    주간/월간 뷰를 위한 도메인 개념
    
    Bug Fix: 커스텀 __init__ 제거
    - Strawberry는 타입 어노테이션을 기반으로 자동으로 __init__ 생성
    - 커스텀 __init__은 Strawberry의 내부 메커니즘과 충돌 가능
    """
    days: List[Day]
