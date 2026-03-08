"""
Visibility - Todo 도메인 E2E 테스트

Todo 가시성 설정 및 접근 제어 통합 테스트
"""
import pytest


def _make_todo(client, title="테스트 Todo"):
    group_id = client.post(
        "/v1/tags/groups", json={"name": "업무", "color": "#FF5733"}
    ).json()["id"]
    return client.post(
        "/v1/todos",
        json={"title": title, "tag_group_id": group_id},
    ).json()["id"]


@pytest.mark.e2e
def test_set_and_get_visibility_todo(e2e_client):
    """Todo 가시성 설정 및 조회 E2E 테스트"""
    todo_id = _make_todo(e2e_client, "가시성 테스트 Todo")

    vis_response = e2e_client.put(
        f"/v1/visibility/todo/{todo_id}",
        json={"level": "friends"},
    )
    assert vis_response.status_code == 200
    vis_data = vis_response.json()
    assert vis_data["level"] == "friends"
    assert vis_data["resource_type"] == "todo"
    assert vis_data["resource_id"] == todo_id

    get_response = e2e_client.get(f"/v1/visibility/todo/{todo_id}")
    assert get_response.status_code == 200
    assert get_response.json()["level"] == "friends"


@pytest.mark.e2e
def test_set_visibility_allowed_emails_todo(e2e_client):
    """Todo ALLOWED_EMAILS 가시성 설정 E2E 테스트"""
    todo_id = _make_todo(e2e_client, "이메일 공개 Todo")

    vis_response = e2e_client.put(
        f"/v1/visibility/todo/{todo_id}",
        json={
            "level": "allowed_emails",
            "allowed_emails": ["alice@example.com"],
            "allowed_domains": ["company.com"],
        },
    )
    assert vis_response.status_code == 200
    data = vis_response.json()
    assert data["level"] == "allowed_emails"
    assert "alice@example.com" in data["allowed_emails"]
    assert "company.com" in data["allowed_domains"]


@pytest.mark.e2e
def test_todo_visibility_public_access(multi_user_e2e):
    """전체 공개 Todo는 다른 사용자도 조회 가능 E2E 테스트"""
    client_a = multi_user_e2e.as_user("user-a")
    client_b = multi_user_e2e.as_user("user-b")

    todo_id = _make_todo(client_a, "전체 공개 Todo")
    client_a.put(f"/v1/visibility/todo/{todo_id}", json={"level": "public"})

    response = client_b.get(f"/v1/todos/{todo_id}")
    assert response.status_code == 200
    assert response.json()["is_shared"] is True


@pytest.mark.e2e
def test_todo_visibility_private_blocks_access(multi_user_e2e):
    """비공개 Todo는 다른 사용자가 조회 불가 E2E 테스트"""
    client_a = multi_user_e2e.as_user("user-a")
    client_b = multi_user_e2e.as_user("user-b")

    todo_id = _make_todo(client_a, "비공개 Todo")

    response = client_b.get(f"/v1/todos/{todo_id}")
    assert response.status_code == 403
