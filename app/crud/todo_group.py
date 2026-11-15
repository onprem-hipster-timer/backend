"""
TodoGroup CRUD Operations

- CRUD는 단순 데이터베이스 작업만 수행
- 비즈니스 로직은 Service에서 처리
- commit은 세션 의존성이 처리
"""
from typing import List, Optional
from uuid import UUID

from sqlmodel import Session, select

from app.domain.todo_group.schema.dto import TodoGroupUpdate
from app.models.todo_group import TodoGroup


def create_todo_group(session: Session, todo_group: TodoGroup) -> TodoGroup:
    """할 일 그룹 생성. todo_group에는 owner_id가 설정되어 있어야 한다"""
    session.add(todo_group)
    session.flush()
    session.refresh(todo_group)
    return todo_group


def get_todo_group(session: Session, group_id: UUID, owner_id: str) -> Optional[TodoGroup]:
    """할 일 그룹 조회 (owner_id 검증 포함)"""
    statement = (
        select(TodoGroup)
        .where(TodoGroup.id == group_id)
        .where(TodoGroup.owner_id == owner_id)
    )
    return session.exec(statement).first()


def get_default_todo_group(session: Session, owner_id: str) -> Optional[TodoGroup]:
    """소유자의 기본 할 일 그룹. 없으면 None"""
    statement = (
        select(TodoGroup)
        .where(TodoGroup.owner_id == owner_id)
        .where(TodoGroup.is_default)
    )
    return session.exec(statement).first()


def get_all_todo_groups(session: Session, owner_id: str) -> List[TodoGroup]:
    """소유자의 모든 할 일 그룹. 기본 그룹이 먼저, 나머지는 이름순"""
    statement = (
        select(TodoGroup)
        .where(TodoGroup.owner_id == owner_id)
        .order_by(TodoGroup.is_default.desc(), TodoGroup.name)
    )
    return list(session.exec(statement).all())


def update_todo_group(session: Session, todo_group: TodoGroup, data: TodoGroupUpdate) -> TodoGroup:
    """할 일 그룹 업데이트"""
    todo_group.apply_update(data.model_dump())
    session.flush()
    session.refresh(todo_group)
    return todo_group


def delete_todo_group(session: Session, todo_group: TodoGroup) -> None:
    """할 일 그룹 삭제"""
    session.delete(todo_group)
