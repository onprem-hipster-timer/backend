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


def get_todo(session: Session, todo_id: UUID, owner_id: str) -> Todo | None:
    """
    ID로 Todo 조회 (owner_id 검증 포함)
    """
    statement = (
        select(Todo)
        .where(Todo.id == todo_id)
        .where(Todo.owner_id == owner_id)
    )
    return session.exec(statement).first()


def get_todo_by_id(session: Session, todo_id: UUID) -> Todo | None:
    """
    ID로 Todo 조회 (소유자 검증 없음 - 접근 제어는 Service에서 처리)
    
    공유 리소스 접근 시 사용
    """
    return session.get(Todo, todo_id)


def get_todos_sorted(
        session: Session,
        owner_id: str,
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
        .where(Todo.owner_id == owner_id)
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


def get_children_by_parent_id(session: Session, parent_id: UUID, owner_id: str) -> List[Todo]:
    """
    특정 부모의 자식 Todo 조회
    """
    statement = (
        select(Todo)
        .where(Todo.owner_id == owner_id)
        .where(Todo.parent_id == parent_id)
    )
    return list(session.exec(statement).all())


def detach_children(session: Session, parent_id: UUID, owner_id: str) -> int:
    """
    부모의 자식 Todo들을 루트로 승격 (parent_id를 NULL로 설정)
    
    부모 삭제 전에 호출하여 자식 Todo가 삭제되지 않고 루트로 이동하도록 함.
    
    :param session: DB 세션
    :param parent_id: 부모 Todo ID
    :param owner_id: 소유자 ID
    :return: 업데이트된 자식 수
    """
    children = get_children_by_parent_id(session, parent_id, owner_id)
    for child in children:
        child.parent_id = None
    session.flush()
    return len(children)


def create_todo(session: Session, todo: Todo) -> Todo:
    """
    Todo 생성 (모델 객체를 받아 저장)
    
    Note: todo 객체는 이미 owner_id가 설정되어 있어야 합니다.
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
