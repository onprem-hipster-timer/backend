"""
TodoGroup Service Tests
"""
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlmodel import select

from app.domain.todo_group.exceptions import (
    DefaultTodoGroupDeletionError,
    TodoGroupNotFoundError,
)
from app.domain.todo_group.schema.dto import TodoGroupCreate, TodoGroupUpdate
from app.domain.todo_group.service import (
    DEFAULT_TODO_GROUP_COLOR,
    DEFAULT_TODO_GROUP_NAME,
    TodoGroupService,
)
from app.models.todo_group import TodoGroup


def _defaults(session, owner_id: str) -> list[TodoGroup]:
    statement = select(TodoGroup).where(TodoGroup.owner_id == owner_id).where(TodoGroup.is_default)
    return list(session.exec(statement).all())


def test_create_todo_group_is_not_default(test_session, test_user):
    group = TodoGroupService(test_session, test_user).create_todo_group(
        TodoGroupCreate(name="업무", color="#FF5733", description="회사 일"),
    )

    assert group.name == "업무"
    assert group.color == "#FF5733"
    assert group.description == "회사 일"
    assert group.owner_id == test_user.sub
    assert group.is_default is False


def test_create_rejects_invalid_color():
    with pytest.raises(ValidationError):
        TodoGroupCreate(name="업무", color="빨강")


def test_get_or_create_default_makes_one_and_reuses_it(test_session, test_user):
    service = TodoGroupService(test_session, test_user)

    first = service.get_or_create_default()
    second = service.get_or_create_default()

    assert first.id == second.id
    assert first.is_default is True
    assert first.name == DEFAULT_TODO_GROUP_NAME
    assert first.color == DEFAULT_TODO_GROUP_COLOR
    assert [g.id for g in _defaults(test_session, test_user.sub)] == [first.id]


def test_default_groups_are_per_owner(test_session, test_user, other_user):
    mine = TodoGroupService(test_session, test_user).get_or_create_default()
    theirs = TodoGroupService(test_session, other_user).get_or_create_default()

    assert mine.id != theirs.id
    assert theirs.owner_id == other_user.sub


def test_get_all_ensures_default_and_lists_it_first(test_session, test_user):
    service = TodoGroupService(test_session, test_user)
    service.create_todo_group(TodoGroupCreate(name="가족", color="#00FF00"))
    service.create_todo_group(TodoGroupCreate(name="공부", color="#0000FF"))

    groups = service.get_all_todo_groups()

    assert [g.name for g in groups] == [DEFAULT_TODO_GROUP_NAME, "가족", "공부"]
    assert [g.is_default for g in groups] == [True, False, False]


def test_get_all_does_not_make_a_second_default(test_session, test_user):
    service = TodoGroupService(test_session, test_user)

    service.get_all_todo_groups()
    service.get_all_todo_groups()

    assert len(_defaults(test_session, test_user.sub)) == 1


def test_default_group_name_and_color_can_change(test_session, test_user):
    service = TodoGroupService(test_session, test_user)
    default = service.get_or_create_default()

    updated = service.update_todo_group(
        default.id, TodoGroupUpdate(name="받은 할 일", color="#123456"),
    )

    assert updated.name == "받은 할 일"
    assert updated.color == "#123456"
    assert updated.is_default is True
    assert service.get_or_create_default().id == default.id


def test_update_cannot_change_is_default(test_session, test_user):
    """수정 DTO에는 is_default가 없어 보내도 무시된다"""
    service = TodoGroupService(test_session, test_user)
    group = service.create_todo_group(TodoGroupCreate(name="업무", color="#FF5733"))

    updated = service.update_todo_group(group.id, TodoGroupUpdate.model_validate({"is_default": True}))

    assert updated.is_default is False
    assert _defaults(test_session, test_user.sub) == []


def test_create_cannot_make_a_default(test_session, test_user):
    """생성 DTO에는 is_default가 없어 보내도 일반 그룹이 된다"""
    group = TodoGroupService(test_session, test_user).create_todo_group(
        TodoGroupCreate.model_validate({"name": "업무", "color": "#FF5733", "is_default": True}),
    )

    assert group.is_default is False


def test_delete_default_group_is_refused(test_session, test_user):
    service = TodoGroupService(test_session, test_user)
    default = service.get_or_create_default()

    with pytest.raises(DefaultTodoGroupDeletionError):
        service.delete_todo_group(default.id)

    assert service.get_todo_group(default.id).id == default.id


def test_delete_other_group(test_session, test_user):
    service = TodoGroupService(test_session, test_user)
    group = service.create_todo_group(TodoGroupCreate(name="업무", color="#FF5733"))

    service.delete_todo_group(group.id)
    test_session.flush()

    with pytest.raises(TodoGroupNotFoundError):
        service.get_todo_group(group.id)


def test_other_owners_group_is_not_found(test_session, test_user, other_user):
    group = TodoGroupService(test_session, other_user).create_todo_group(
        TodoGroupCreate(name="남의 그룹", color="#FF5733"),
    )
    service = TodoGroupService(test_session, test_user)

    with pytest.raises(TodoGroupNotFoundError):
        service.get_todo_group(group.id)
    with pytest.raises(TodoGroupNotFoundError):
        service.update_todo_group(group.id, TodoGroupUpdate(name="바꿈"))
    with pytest.raises(TodoGroupNotFoundError):
        service.delete_todo_group(group.id)
    with pytest.raises(TodoGroupNotFoundError):
        service.get_todo_group(uuid4())
