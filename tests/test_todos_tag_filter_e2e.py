"""
Todo 목록 태그 필터 E2E 테스트 (GET /v1/todos의 tag_ids, tag_match)
"""
from uuid import uuid4

import pytest


def _tag_group(client, name):
    return client.post("/v1/tags/groups", json={"name": name, "color": "#FF5733"}).json()["id"]


def _tag(client, group_id, name):
    response = client.post("/v1/tags", json={"name": name, "color": "#00FF00", "group_id": group_id})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _todo(client, title, **fields):
    response = client.post("/v1/todos", json={"title": title, **fields})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _list(client, **params):
    response = client.get("/v1/todos", params=params)
    assert response.status_code == 200, response.text
    return {t["id"]: t["include_reason"] for t in response.json()}


@pytest.fixture
def tagged(e2e_client):
    """서로 다른 태그 그룹의 태그 a, b와 각 조합의 Todo"""
    a = _tag(e2e_client, _tag_group(e2e_client, "업무"), "a")
    b = _tag(e2e_client, _tag_group(e2e_client, "개인"), "b")
    return {
        "a": a,
        "b": b,
        "only_a": _todo(e2e_client, "a만", tag_ids=[a]),
        "only_b": _todo(e2e_client, "b만", tag_ids=[b]),
        "both": _todo(e2e_client, "a와 b", tag_ids=[a, b]),
        "none": _todo(e2e_client, "태그 없음"),
    }


@pytest.mark.e2e
def test_tag_match_all_requires_every_tag(e2e_client, tagged):
    result = _list(e2e_client, tag_ids=[tagged["a"], tagged["b"]], tag_match="all")

    assert set(result) == {tagged["both"]}


@pytest.mark.e2e
def test_tag_match_defaults_to_all(e2e_client, tagged):
    result = _list(e2e_client, tag_ids=[tagged["a"], tagged["b"]])

    assert set(result) == {tagged["both"]}


@pytest.mark.e2e
def test_tag_match_any_requires_one_tag(e2e_client, tagged):
    result = _list(e2e_client, tag_ids=[tagged["a"], tagged["b"]], tag_match="any")

    assert set(result) == {tagged["only_a"], tagged["only_b"], tagged["both"]}
    assert set(result.values()) == {"MATCH"}


@pytest.mark.e2e
def test_tag_match_any_includes_ancestors(e2e_client, tagged):
    grandparent = _todo(e2e_client, "조부모")
    parent = _todo(e2e_client, "부모", parent_id=grandparent)
    child = _todo(e2e_client, "자식", parent_id=parent, tag_ids=[tagged["b"]])

    result = _list(e2e_client, tag_ids=[tagged["a"], tagged["b"]], tag_match="any")

    assert result[child] == "MATCH"
    assert result[parent] == "ANCESTOR"
    assert result[grandparent] == "ANCESTOR"
    assert tagged["none"] not in result


@pytest.mark.e2e
def test_tag_match_without_tag_ids_returns_everything(e2e_client, tagged):
    assert _list(e2e_client, tag_match="any") == _list(e2e_client)
    assert tagged["none"] in _list(e2e_client, tag_match="any")


@pytest.mark.e2e
def test_tag_match_any_combined_with_todo_group_ids(e2e_client, tagged):
    other_group = e2e_client.post("/v1/todos/groups", json={"name": "다른 그룹", "color": "#0000FF"}).json()["id"]
    in_other_group = _todo(e2e_client, "다른 그룹의 a", todo_group_id=other_group, tag_ids=[tagged["a"]])
    _todo(e2e_client, "다른 그룹의 태그 없음", todo_group_id=other_group)

    result = _list(
        e2e_client, tag_ids=[tagged["a"], tagged["b"]], tag_match="any", todo_group_ids=[other_group]
    )

    assert set(result) == {in_other_group}


@pytest.mark.e2e
@pytest.mark.parametrize("tag_match", ["all", "any"])
def test_unknown_tag_id_matches_nothing(e2e_client, tagged, tag_match):
    assert _list(e2e_client, tag_ids=[str(uuid4())], tag_match=tag_match) == {}


@pytest.mark.e2e
def test_any_ignores_unknown_tag_id_next_to_known_one(e2e_client, tagged):
    result = _list(e2e_client, tag_ids=[tagged["a"], str(uuid4())], tag_match="any")

    assert set(result) == {tagged["only_a"], tagged["both"]}


@pytest.mark.e2e
def test_invalid_tag_match_is_rejected(e2e_client, tagged):
    response = e2e_client.get("/v1/todos", params={"tag_ids": [tagged["a"]], "tag_match": "some"})

    assert response.status_code == 422


@pytest.mark.e2e
@pytest.mark.parametrize("tag_match", ["all", "any"])
def test_other_users_tag_does_not_match_own_todos(multi_user_e2e, tag_match):
    client_a = multi_user_e2e.as_user("user-a")
    client_b = multi_user_e2e.as_user("user-b")
    tag_a = _tag(client_a, _tag_group(client_a, "A 그룹"), "a")
    tag_b = _tag(client_b, _tag_group(client_b, "B 그룹"), "b")
    _todo(client_a, "A의 할 일", tag_ids=[tag_a])

    assert _list(client_a, tag_ids=[tag_b], tag_match=tag_match) == {}


@pytest.mark.e2e
def test_tag_match_applies_to_shared_todos(multi_user_e2e):
    client_a = multi_user_e2e.as_user("user-a")
    client_b = multi_user_e2e.as_user("user-b")
    group = _tag_group(client_a, "A 그룹")
    a = _tag(client_a, group, "a")
    b = _tag(client_a, group, "b")
    only_a = _todo(client_a, "a만", tag_ids=[a])
    both = _todo(client_a, "a와 b", tag_ids=[a, b])
    untagged = _todo(client_a, "태그 없음")
    for todo_id in (only_a, both, untagged):
        client_a.put(f"/v1/visibility/todo/{todo_id}", json={"level": "public"})

    assert set(_list(client_b, scope="shared", tag_ids=[a, b], tag_match="all")) == {both}
    assert set(_list(client_b, scope="shared", tag_ids=[a, b], tag_match="any")) == {only_a, both}
