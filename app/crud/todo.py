"""
Todo CRUD Operations

FastAPI Best Practices:
- CRUD는 데이터 접근만 담당
- 비즈니스 로직 없음
- commit은 get_db_transactional이 처리
"""
from typing import List, Optional
from uuid import UUID

from sqlalchemy import case
from sqlmodel import Session, select

from app.domain.todo.enums import TodoStatus
from app.models.tag import TodoTag
from app.models.todo import Todo

# 정렬 우선순위용 상태 순서
STATUS_ORDER: dict[TodoStatus, int] = {
    TodoStatus.UNSCHEDULED: 0,
    TodoStatus.SCHEDULED: 1,
    TodoStatus.DONE: 2,
    TodoStatus.CANCELLED: 3,
}


def get_todo(session: Session, todo_id: UUID) -> Todo | None:
    """
    ID로 Todo 조회
    """
    return session.get(Todo, todo_id)


def get_todos_sorted(
        session: Session,
        group_ids: Optional[List[UUID]] = None,
        parent_id: Optional[UUID] = None,
) -> List[Todo]:
    """
    Todo 목록 조회 (정렬 적용)
    
    정렬: STATUS_ORDER → deadline(null last) → created_at desc
    """
    status_order_expr = case(
        {status.value: order for status, order in STATUS_ORDER.items()},
        value=Todo.status,
        else_=999,
    )
    deadline_null_expr = case(
        (Todo.deadline.is_(None), 1),
        else_=0,
    )
    
    statement = (
        select(Todo)
        .order_by(
            status_order_expr,
            deadline_null_expr,
            Todo.deadline.asc(),
            Todo.created_at.desc(),
        )
    )
    
    if group_ids:
        statement = statement.where(Todo.tag_group_id.in_(group_ids))
    if parent_id is not None:
        statement = statement.where(Todo.parent_id == parent_id)
    
    return list(session.exec(statement).all())


def get_todo_tag_map(
        session: Session,
        todo_ids: List[UUID],
) -> dict[UUID, set[UUID]]:
    """
    Todo ID 목록에 대한 태그 매핑 조회
    
    :return: {todo_id: {tag_id, ...}, ...}
    """
    if not todo_ids:
        return {}
    
    statement = (
        select(TodoTag.todo_id, TodoTag.tag_id)
        .where(TodoTag.todo_id.in_(todo_ids))
    )
    rows = session.exec(statement).all()
    
    result: dict[UUID, set[UUID]] = {}
    for todo_id, tag_id in rows:
        result.setdefault(todo_id, set()).add(tag_id)
    
    return result


def get_children_by_parent_id(session: Session, parent_id: UUID) -> List[Todo]:
    """
    특정 부모의 자식 Todo 조회
    """
    statement = select(Todo).where(Todo.parent_id == parent_id)
    return list(session.exec(statement).all())


def create_todo(session: Session, todo: Todo) -> Todo:
    """
    Todo 생성 (모델 객체를 받아 저장)
    """
    session.add(todo)
    session.flush()
    session.refresh(todo)
    return todo


def delete_todo(session: Session, todo: Todo) -> None:
    """
    Todo 삭제
    """
    session.delete(todo)
