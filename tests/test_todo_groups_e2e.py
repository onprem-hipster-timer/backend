"""
TodoGroup E2E Tests
"""
import pytest

from app.domain.todo_group.service import DEFAULT_TODO_GROUP_NAME
from app.ratelimit.config import get_rule_for_request


@pytest.mark.e2e
def test_list_route_is_not_taken_by_todo_id(e2e_client):
    """`/groups`가 `/{todo_id}`로 해석되면 422가 난다"""
    response = e2e_client.get("/v1/todos/groups")

    assert response.status_code == 200


@pytest.mark.e2e
def test_list_ensures_default_first(e2e_client):
    e2e_client.post("/v1/todos/groups", json={"name": "가족", "color": "#00FF00"})

    groups = e2e_client.get("/v1/todos/groups").json()

    assert [g["name"] for g in groups] == [DEFAULT_TODO_GROUP_NAME, "가족"]
    assert [g["is_default"] for g in groups] == [True, False]


@pytest.mark.e2e
def test_list_twice_keeps_one_default(e2e_client):
    first = e2e_client.get("/v1/todos/groups").json()
    second = e2e_client.get("/v1/todos/groups").json()

    assert [g["id"] for g in first] == [g["id"] for g in second]
    assert sum(g["is_default"] for g in second) == 1


@pytest.mark.e2e
def test_create_read_update_delete(e2e_client):
    created = e2e_client.post(
        "/v1/todos/groups",
        json={"name": "업무", "color": "#FF5733", "description": "회사 일", "is_default": True},
    )
    assert created.status_code == 201
    group = created.json()
    assert group["is_default"] is False

    assert e2e_client.get(f"/v1/todos/groups/{group['id']}").json()["name"] == "업무"

    patched = e2e_client.patch(f"/v1/todos/groups/{group['id']}", json={"name": "회사"})
    assert patched.status_code == 200
    assert patched.json()["name"] == "회사"

    assert e2e_client.delete(f"/v1/todos/groups/{group['id']}").status_code == 200
    assert e2e_client.get(f"/v1/todos/groups/{group['id']}").status_code == 404


@pytest.mark.e2e
def test_default_group_can_be_renamed_but_not_deleted(e2e_client):
    default = e2e_client.get("/v1/todos/groups").json()[0]

    renamed = e2e_client.patch(f"/v1/todos/groups/{default['id']}", json={"name": "받은 할 일"})
    deleted = e2e_client.delete(f"/v1/todos/groups/{default['id']}")

    assert renamed.status_code == 200
    assert renamed.json()["is_default"] is True
    assert deleted.status_code == 409
    assert e2e_client.get(f"/v1/todos/groups/{default['id']}").status_code == 200


@pytest.mark.e2e
def test_other_users_group_is_not_found(multi_user_e2e):
    owner = multi_user_e2e.as_user("owner")
    stranger = multi_user_e2e.as_user("stranger")
    group = owner.post("/v1/todos/groups", json={"name": "업무", "color": "#FF5733"}).json()

    assert stranger.get(f"/v1/todos/groups/{group['id']}").status_code == 404
    assert stranger.patch(f"/v1/todos/groups/{group['id']}", json={"name": "x"}).status_code == 404
    assert stranger.delete(f"/v1/todos/groups/{group['id']}").status_code == 404
    assert [g["is_default"] for g in stranger.get("/v1/todos/groups").json()] == [True]


def test_creating_groups_has_its_own_rate_limit_rule():
    """할 일 그룹 생성은 할 일 경로 전체 규칙이 아니라 쓰기 규칙을 따로 쓴다"""
    rule = get_rule_for_request("POST", "/v1/todos/groups")

    assert rule is not None
    assert rule.path_pattern == "/v1/todos/groups"
    assert rule.max_requests == get_rule_for_request("POST", "/v1/tags/groups").max_requests


# ============================================================
# 할 일과 할 일 그룹
# ============================================================

@pytest.mark.e2e
def test_todo_without_group_goes_to_default(e2e_client):
    first = e2e_client.post("/v1/todos", json={"title": "첫 할 일"})
    second = e2e_client.post("/v1/todos", json={"title": "둘째 할 일"})

    groups = e2e_client.get("/v1/todos/groups").json()
    assert first.status_code == 201
    assert [g["is_default"] for g in groups] == [True]
    assert first.json()["todo_group_id"] == groups[0]["id"]
    assert second.json()["todo_group_id"] == groups[0]["id"]


@pytest.mark.e2e
def test_todo_into_other_users_group_is_not_found(multi_user_e2e):
    owner = multi_user_e2e.as_user("owner")
    stranger = multi_user_e2e.as_user("stranger")
    group_id = owner.post("/v1/todos/groups", json={"name": "업무", "color": "#FF5733"}).json()["id"]

    response = stranger.post("/v1/todos", json={"title": "끼어들기", "todo_group_id": group_id})

    assert response.status_code == 404
    assert owner.get("/v1/todos", params={"todo_group_ids": [group_id]}).json() == []


@pytest.mark.e2e
def test_deleting_group_moves_its_todo_tree_to_default(e2e_client):
    group_id = e2e_client.post("/v1/todos/groups", json={"name": "업무", "color": "#FF5733"}).json()["id"]
    parent = e2e_client.post("/v1/todos", json={"title": "부모", "todo_group_id": group_id}).json()
    child = e2e_client.post(
        "/v1/todos", json={"title": "자식", "todo_group_id": group_id, "parent_id": parent["id"]},
    ).json()

    deleted = e2e_client.delete(f"/v1/todos/groups/{group_id}")

    default_id = e2e_client.get("/v1/todos/groups").json()[0]["id"]
    moved_parent = e2e_client.get(f"/v1/todos/{parent['id']}").json()
    moved_child = e2e_client.get(f"/v1/todos/{child['id']}").json()
    assert deleted.status_code == 200
    assert moved_parent["todo_group_id"] == default_id
    assert moved_child["todo_group_id"] == default_id
    assert moved_child["parent_id"] == parent["id"]
    assert e2e_client.get(f"/v1/todos/groups/{group_id}").status_code == 404



@pytest.mark.e2e
def test_patching_group_moves_subtree(e2e_client):
    work = e2e_client.post("/v1/todos/groups", json={"name": "업무", "color": "#FF5733"}).json()["id"]
    personal = e2e_client.post("/v1/todos/groups", json={"name": "개인", "color": "#3366FF"}).json()["id"]
    root = e2e_client.post("/v1/todos", json={"title": "root", "todo_group_id": work}).json()
    child = e2e_client.post("/v1/todos", json={"title": "child", "todo_group_id": work, "parent_id": root["id"]}).json()
    leaf = e2e_client.post("/v1/todos", json={"title": "leaf", "todo_group_id": work, "parent_id": child["id"]}).json()

    moved = e2e_client.patch(f"/v1/todos/{child['id']}", json={"todo_group_id": personal})

    assert moved.status_code == 200
    assert (moved.json()["todo_group_id"], moved.json()["parent_id"]) == (personal, None)
    saved_leaf = e2e_client.get(f"/v1/todos/{leaf['id']}").json()
    assert (saved_leaf["todo_group_id"], saved_leaf["parent_id"]) == (personal, child["id"])
    assert e2e_client.get(f"/v1/todos/{root['id']}").json()["todo_group_id"] == work


@pytest.mark.e2e
def test_patching_into_other_users_group_is_not_found(multi_user_e2e):
    owner = multi_user_e2e.as_user("owner")
    stranger = multi_user_e2e.as_user("stranger")
    group_id = owner.post("/v1/todos/groups", json={"name": "업무", "color": "#FF5733"}).json()["id"]
    todo = stranger.post("/v1/todos", json={"title": "내 할 일"}).json()

    response = stranger.patch(f"/v1/todos/{todo['id']}", json={"todo_group_id": group_id})

    assert response.status_code == 404
    assert stranger.get(f"/v1/todos/{todo['id']}").json()["todo_group_id"] == todo["todo_group_id"]
