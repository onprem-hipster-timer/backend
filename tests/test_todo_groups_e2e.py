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
