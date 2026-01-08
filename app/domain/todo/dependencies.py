"""
Todo Domain Dependencies

FastAPI Dependency Injection을 위한 함수들
"""
from uuid import UUID

from fastapi import Depends
from sqlmodel import Session

from app.db.session import get_db_transactional
from app.domain.todo.exceptions import TodoNotFoundError, NotATodoError
from app.domain.todo.model import Todo


def valid_todo_id(
        todo_id: UUID,
        session: Session = Depends(get_db_transactional),
) -> Todo:
    """
    Todo ID 검증 및 조회
    
    :param todo_id: Todo ID
    :param session: DB 세션
    :return: Todo 객체
    :raises TodoNotFoundError: Todo를 찾을 수 없는 경우
    :raises NotATodoError: 일정이 Todo가 아닌 경우
    """
    todo = session.get(Todo, todo_id)
    if not todo:
        raise TodoNotFoundError()
    
    # Todo인지 확인 (is_todo 필드 사용)
    if not todo.is_todo:
        raise NotATodoError()
    
    return todo

