"""
TodoGroup Domain Service

할 일 그룹의 생성·조회·수정·삭제와 기본 그룹 보장을 맡는다.
기본 그룹은 사용자당 하나이고, 지울 수 없다.

테스트: tests/domain/todo_group/test_service.py, tests/test_todo_groups_e2e.py
"""
from typing import List, Optional
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.core.auth import CurrentUser
from app.crud import todo as todo_crud
from app.crud import todo_group as crud
from app.domain.todo_group.exceptions import (
    DefaultTodoGroupDeletionError,
    TodoGroupNotFoundError,
)
from app.domain.todo_group.schema.dto import TodoGroupCreate, TodoGroupUpdate
from app.models.todo_group import TodoGroup

DEFAULT_TODO_GROUP_NAME = "기본"
DEFAULT_TODO_GROUP_COLOR = "#2196F3"


def _raise_group_not_found(group_id: UUID) -> None:
    raise TodoGroupNotFoundError(f"할 일 그룹을 찾을 수 없습니다: {group_id}")


class TodoGroupService:
    """할 일 그룹 도메인 서비스. CurrentUser 기준으로 사용자별 데이터를 나눈다"""

    def __init__(self, session: Session, current_user: CurrentUser):
        self.session = session
        self.current_user = current_user
        self.owner_id = current_user.sub

    def create_todo_group(self, data: TodoGroupCreate) -> TodoGroup:
        """할 일 그룹 생성. 기본 그룹은 만들 수 없다"""
        todo_group = TodoGroup.model_validate({**data.model_dump(), "owner_id": self.owner_id})
        return crud.create_todo_group(self.session, todo_group)

    def get_todo_group(self, group_id: UUID) -> TodoGroup:
        """할 일 그룹 조회. 남의 그룹이거나 없으면 404"""
        todo_group = crud.get_todo_group(self.session, group_id, self.owner_id)
        if not todo_group:
            _raise_group_not_found(group_id)
        return todo_group

    def get_all_todo_groups(self) -> List[TodoGroup]:
        """모든 할 일 그룹. 기본 그룹을 보장한 뒤 기본 먼저, 나머지는 이름순"""
        self.get_or_create_default()
        return crud.get_all_todo_groups(self.session, self.owner_id)

    def update_todo_group(self, group_id: UUID, data: TodoGroupUpdate) -> TodoGroup:
        """할 일 그룹의 이름·색·설명 수정. 기본 그룹도 바꿀 수 있다"""
        return crud.update_todo_group(self.session, self.get_todo_group(group_id), data)

    def delete_todo_group(self, group_id: UUID) -> None:
        """할 일 그룹 삭제. 그룹의 할 일은 트리 모양 그대로 기본 그룹으로 옮긴다. 기본 그룹이면 409"""
        todo_group = self.get_todo_group(group_id)
        if todo_group.is_default:
            raise DefaultTodoGroupDeletionError()
        default = self.get_or_create_default()
        todo_crud.move_todos_to_group(self.session, self.owner_id, todo_group.id, default.id)
        crud.delete_todo_group(self.session, todo_group)

    def resolve_group_id(self, group_id: Optional[UUID]) -> UUID:
        """할 일이 들어갈 그룹 id. 주면 내 그룹인지 확인하고(아니면 404), 안 주면 기본 그룹"""
        if group_id is None:
            return self.get_or_create_default().id
        return self.get_todo_group(group_id).id

    def get_or_create_default(self) -> TodoGroup:
        """기본 그룹을 돌려준다. 없으면 만든다.

        같은 사용자의 요청 둘이 동시에 만들려 하면 부분 unique 인덱스(uq_todo_group_owner_default)가
        하나만 남긴다. 진 쪽은 SAVEPOINT만 되돌리고 이긴 쪽의 그룹을 다시 읽는다.
        앞서 쌓인 변경은 SAVEPOINT 밖에서 먼저 flush해, 그 변경의 IntegrityError를 여기서 삼키지 않는다.
        """
        existing = crud.get_default_todo_group(self.session, self.owner_id)
        if existing:
            return existing

        self.session.flush()
        todo_group = TodoGroup(
            owner_id=self.owner_id,
            name=DEFAULT_TODO_GROUP_NAME,
            color=DEFAULT_TODO_GROUP_COLOR,
            is_default=True,
        )
        try:
            with self.session.begin_nested():
                self.session.add(todo_group)
                self.session.flush()
        except IntegrityError:
            existing = crud.get_default_todo_group(self.session, self.owner_id)
            if existing is None:
                raise
            return existing
        return todo_group
