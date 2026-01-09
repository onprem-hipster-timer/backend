"""
Todo Router

FastAPI Best Practices:
- 모든 라우트는 async
- Service는 session을 받아서 CRUD 직접 사용
- Todo 전용 엔드포인트 (Schedule과 분리)
"""
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session

from app.db.session import get_db_transactional
from app.domain.todo.dependencies import valid_todo_id
from app.domain.todo.model import Todo
from app.domain.todo.schema.dto import (
    TodoCreate,
    TodoRead,
    TodoUpdate,
    TodoStats,
)
from app.domain.todo.service import TodoService

router = APIRouter(prefix="/todos", tags=["Todos"])


@router.post("", response_model=TodoRead, status_code=status.HTTP_201_CREATED)
async def create_todo(
        data: TodoCreate,
        session: Session = Depends(get_db_transactional),
):
    """
    새 Todo 생성
    
    Todo는 독립적인 엔티티입니다.
    deadline이 있으면 별도의 Schedule이 자동으로 생성됩니다.
    """
    service = TodoService(session)
    todo = service.create_todo(data)
    return service.to_read_dto(todo)


@router.get("", response_model=list[TodoRead])
async def read_todos(
        tag_ids: Optional[List[UUID]] = Query(
            None,
            description="태그 ID 리스트 (AND 방식: 모든 지정 태그를 포함한 Todo만 반환)"
        ),
        group_ids: Optional[List[UUID]] = Query(
            None,
            description="태그 그룹 ID 리스트 (해당 그룹에 속한 Todo 반환 - 직접 연결 또는 태그 기반)"
        ),
        session: Session = Depends(get_db_transactional),
):
    """
    Todo 목록 조회 (태그/그룹 필터링 지원)
    
    그룹 필터링:
    - group_ids: 해당 그룹에 속한 Todo 반환
      - tag_group_id로 직접 연결된 Todo
      - OR 해당 그룹의 태그를 가진 Todo
    
    태그 필터링:
    - tag_ids: AND 방식 (모든 지정 태그를 포함한 Todo만 반환)
    
    둘 다 지정 시: 그룹 필터링 후 태그 필터링 적용
    """
    service = TodoService(session)
    todos = service.get_all_todos(tag_ids=tag_ids, group_ids=group_ids)
    return [service.to_read_dto(todo) for todo in todos]


@router.get("/stats", response_model=TodoStats)
async def get_todo_stats(
        group_id: Optional[UUID] = Query(
            None,
            description="필터링할 태그 그룹 ID"
        ),
        session: Session = Depends(get_db_transactional),
):
    """
    Todo 통계 조회
    
    그룹별 태그 통계를 반환합니다.
    group_id가 지정되면 해당 그룹의 태그만 집계합니다.
    """
    service = TodoService(session)
    return service.get_todo_stats(group_id=group_id)


@router.get("/{todo_id}", response_model=TodoRead)
async def read_todo(
        todo: Todo = Depends(valid_todo_id),
        session: Session = Depends(get_db_transactional),
):
    """
    ID로 Todo 조회
    """
    service = TodoService(session)
    return service.to_read_dto(todo)


@router.patch("/{todo_id}", response_model=TodoRead)
async def update_todo(
        todo_id: UUID,
        data: TodoUpdate,
        session: Session = Depends(get_db_transactional),
):
    """
    Todo 업데이트
    
    title, description, tag_ids, deadline, parent_id, status를 업데이트할 수 있습니다.
    
    deadline 변경 시:
    - deadline 추가: 새 Schedule 생성
    - deadline 변경: 기존 Schedule 업데이트
    - deadline 제거: 기존 Schedule 삭제
    """
    service = TodoService(session)
    todo = service.update_todo(todo_id, data)
    return service.to_read_dto(todo)


@router.delete("/{todo_id}", status_code=status.HTTP_200_OK)
async def delete_todo(
        todo_id: UUID,
        session: Session = Depends(get_db_transactional),
):
    """
    Todo 삭제
    """
    service = TodoService(session)
    service.delete_todo(todo_id)
    return {"ok": True}

