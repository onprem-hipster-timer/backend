"""
할 일을 다른 할 일 그룹으로 옮기기

옮긴 할 일의 하위 할 일은 함께 옮겨지고(트리 모양 그대로), 부모가 옛 그룹에 남으면 연결이 끊긴다.
"""
import pytest

from app.domain.todo.exceptions import TodoParentGroupMismatchError
from app.domain.todo.schema.dto import TodoCreate, TodoUpdate
from app.domain.todo.service import TodoService
from app.domain.todo_group.exceptions import TodoGroupNotFoundError
from app.domain.todo_group.schema.dto import TodoGroupCreate
from app.domain.todo_group.service import TodoGroupService


@pytest.fixture
def groups(test_session, test_user):
    service = TodoGroupService(test_session, test_user)
    return (
        service.create_todo_group(TodoGroupCreate(name="업무", color="#FF5733")),
        service.create_todo_group(TodoGroupCreate(name="개인", color="#3366FF")),
    )


@pytest.fixture
def tree(test_session, test_user, groups):
    """업무 그룹의 root → child → grandchild, 그리고 child의 형제 sibling"""
    work, _ = groups
    service = TodoService(test_session, test_user)
    root = service.create_todo(TodoCreate(title="root", todo_group_id=work.id))
    child = service.create_todo(TodoCreate(title="child", todo_group_id=work.id, parent_id=root.id))
    grandchild = service.create_todo(TodoCreate(title="grandchild", todo_group_id=work.id, parent_id=child.id))
    sibling = service.create_todo(TodoCreate(title="sibling", todo_group_id=work.id, parent_id=root.id))
    test_session.flush()
    return {"root": root, "child": child, "grandchild": grandchild, "sibling": sibling}


def _state(test_session, test_user, todo) -> tuple:
    test_session.expire_all()
    saved = TodoService(test_session, test_user).get_todo(todo.id)
    return saved.todo_group_id, saved.parent_id


def test_moving_root_moves_whole_tree(test_session, test_user, groups, tree):
    _, personal = groups

    TodoService(test_session, test_user).update_todo(tree["root"].id, TodoUpdate(todo_group_id=personal.id))

    assert _state(test_session, test_user, tree["root"]) == (personal.id, None)
    assert _state(test_session, test_user, tree["child"]) == (personal.id, tree["root"].id)
    assert _state(test_session, test_user, tree["grandchild"]) == (personal.id, tree["child"].id)
    assert _state(test_session, test_user, tree["sibling"]) == (personal.id, tree["root"].id)


def test_moving_child_detaches_it_from_parent_left_behind(test_session, test_user, groups, tree):
    work, personal = groups

    TodoService(test_session, test_user).update_todo(tree["child"].id, TodoUpdate(todo_group_id=personal.id))

    assert _state(test_session, test_user, tree["child"]) == (personal.id, None)
    assert _state(test_session, test_user, tree["grandchild"]) == (personal.id, tree["child"].id)
    assert _state(test_session, test_user, tree["root"]) == (work.id, None)
    assert _state(test_session, test_user, tree["sibling"]) == (work.id, tree["root"].id)


def test_same_group_keeps_parent(test_session, test_user, groups, tree):
    work, _ = groups

    TodoService(test_session, test_user).update_todo(tree["child"].id, TodoUpdate(todo_group_id=work.id))

    assert _state(test_session, test_user, tree["child"]) == (work.id, tree["root"].id)


def test_move_with_parent_in_new_group(test_session, test_user, groups, tree):
    _, personal = groups
    service = TodoService(test_session, test_user)
    new_parent = service.create_todo(TodoCreate(title="new parent", todo_group_id=personal.id))

    service.update_todo(tree["child"].id, TodoUpdate(todo_group_id=personal.id, parent_id=new_parent.id))

    assert _state(test_session, test_user, tree["child"]) == (personal.id, new_parent.id)
    assert _state(test_session, test_user, tree["grandchild"]) == (personal.id, tree["child"].id)


def test_move_with_parent_left_in_old_group_is_refused(test_session, test_user, groups, tree):
    _, personal = groups

    with pytest.raises(TodoParentGroupMismatchError):
        TodoService(test_session, test_user).update_todo(
            tree["child"].id, TodoUpdate(todo_group_id=personal.id, parent_id=tree["root"].id),
        )


def test_move_under_own_descendant_is_refused(test_session, test_user, groups, tree):
    """옮기면서 자기 하위를 부모로 고르면 거절한다. 하위는 아직 옛 그룹이라 그룹 검사가 먼저 막는다"""
    work, personal = groups

    with pytest.raises(TodoParentGroupMismatchError):
        TodoService(test_session, test_user).update_todo(
            tree["root"].id, TodoUpdate(todo_group_id=personal.id, parent_id=tree["grandchild"].id),
        )

    assert _state(test_session, test_user, tree["root"]) == (work.id, None)


def test_move_into_other_users_group_changes_nothing(test_session, test_user, other_user, groups, tree):
    work, _ = groups
    stranger_group = TodoGroupService(test_session, other_user).create_todo_group(
        TodoGroupCreate(name="남의 그룹", color="#000000"),
    )

    with pytest.raises(TodoGroupNotFoundError):
        TodoService(test_session, test_user).update_todo(tree["root"].id, TodoUpdate(todo_group_id=stranger_group.id))

    assert _state(test_session, test_user, tree["root"]) == (work.id, None)
    assert _state(test_session, test_user, tree["child"]) == (work.id, tree["root"].id)


def test_null_group_is_ignored(test_session, test_user, groups, tree):
    """todo_group_id: null은 그룹을 비울 수 없으므로 무시한다"""
    work, _ = groups

    TodoService(test_session, test_user).update_todo(tree["child"].id, TodoUpdate(todo_group_id=None))

    assert _state(test_session, test_user, tree["child"]) == (work.id, tree["root"].id)
