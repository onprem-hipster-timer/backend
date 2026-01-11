"""
Todo E2E Tests

HTTP API를 통한 Todo E2E 테스트
"""
from uuid import uuid4

import pytest


@pytest.mark.e2e
def test_create_todo_e2e(e2e_client):
    """HTTP를 통한 Todo 생성 E2E 테스트"""
    # 먼저 태그 그룹 생성 필요
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "업무", "color": "#FF5733"}
    )
    group_id = group_response.json()["id"]
    
    response = e2e_client.post(
        "/v1/todos",
        json={
            "title": "E2E 테스트 Todo",
            "description": "E2E 테스트 설명",
            "tag_group_id": group_id,
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "E2E 테스트 Todo"
    assert data["description"] == "E2E 테스트 설명"
    assert data["status"] == "UNSCHEDULED"
    assert "id" in data
    assert "tags" in data
    assert "schedules" in data


@pytest.mark.e2e
def test_create_todo_with_deadline_e2e(e2e_client):
    """마감 시간이 있는 Todo 생성 E2E 테스트"""
    # 태그 그룹 생성
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "업무", "color": "#FF5733"}
    )
    group_id = group_response.json()["id"]
    
    response = e2e_client.post(
        "/v1/todos",
        json={
            "title": "마감 시간 있는 Todo",
            "tag_group_id": group_id,
            "deadline": "2024-01-01T12:00:00Z",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "마감 시간 있는 Todo"
    assert data["deadline"] is not None
    assert "2024-01-01T12:00:00" in data["deadline"]
    # Schedule이 생성되었는지 확인
    assert len(data["schedules"]) == 1


@pytest.mark.e2e
def test_create_todo_with_tags_e2e(e2e_client):
    """태그와 함께 Todo 생성 E2E 테스트"""
    # 그룹 및 태그 생성
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "업무", "color": "#FF5733"}
    )
    group_id = group_response.json()["id"]

    tag_response = e2e_client.post(
        "/v1/tags",
        json={
            "name": "중요",
            "color": "#FF0000",
            "group_id": group_id,
        }
    )
    tag_id = tag_response.json()["id"]

    # Todo 생성 시 태그 함께 설정
    todo_response = e2e_client.post(
        "/v1/todos",
        json={
            "title": "태그 있는 Todo",
            "tag_group_id": group_id,
            "tag_ids": [tag_id],
        },
    )

    assert todo_response.status_code == 201
    data = todo_response.json()
    assert data["title"] == "태그 있는 Todo"
    assert "tags" in data
    assert len(data["tags"]) == 1
    assert data["tags"][0]["id"] == tag_id


@pytest.mark.e2e
def test_create_todo_with_parent_e2e(e2e_client):
    """부모 Todo가 있는 Todo 생성 E2E 테스트"""
    # 태그 그룹 생성
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "업무", "color": "#FF5733"}
    )
    group_id = group_response.json()["id"]
    
    # 부모 Todo 생성
    parent_response = e2e_client.post(
        "/v1/todos",
        json={
            "title": "부모 Todo",
            "tag_group_id": group_id,
        },
    )
    parent_id = parent_response.json()["id"]
    
    # 자식 Todo 생성
    child_response = e2e_client.post(
        "/v1/todos",
        json={
            "title": "자식 Todo",
            "tag_group_id": group_id,
            "parent_id": parent_id,
        },
    )
    
    assert child_response.status_code == 201
    data = child_response.json()
    assert data["title"] == "자식 Todo"
    assert data["parent_id"] == parent_id


@pytest.mark.e2e
def test_get_todo_e2e(e2e_client):
    """HTTP를 통한 Todo 조회 E2E 테스트"""
    # 태그 그룹 생성
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "업무", "color": "#FF5733"}
    )
    group_id = group_response.json()["id"]
    
    # Todo 생성
    create_response = e2e_client.post(
        "/v1/todos",
        json={
            "title": "조회 테스트 Todo",
            "description": "조회 테스트 설명",
            "tag_group_id": group_id,
        },
    )
    assert create_response.status_code == 201
    todo_id = create_response.json()["id"]

    # Todo 조회
    get_response = e2e_client.get(f"/v1/todos/{todo_id}")
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["id"] == todo_id
    assert data["title"] == "조회 테스트 Todo"
    assert data["description"] == "조회 테스트 설명"
    assert data["status"] == "UNSCHEDULED"


@pytest.mark.e2e
def test_get_todo_not_found_e2e(e2e_client):
    """존재하지 않는 Todo 조회 E2E 테스트"""
    non_existent_id = str(uuid4())
    response = e2e_client.get(f"/v1/todos/{non_existent_id}")

    assert response.status_code == 404
    assert "not found" in response.json()["message"].lower()


@pytest.mark.e2e
def test_get_todos_e2e(e2e_client):
    """HTTP를 통한 Todo 목록 조회 E2E 테스트"""
    # 태그 그룹 생성
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "업무", "color": "#FF5733"}
    )
    group_id = group_response.json()["id"]
    
    # 여러 Todo 생성
    e2e_client.post("/v1/todos", json={"title": "Todo 1", "tag_group_id": group_id})
    e2e_client.post("/v1/todos", json={"title": "Todo 2", "tag_group_id": group_id})
    e2e_client.post("/v1/todos", json={"title": "Todo 3", "tag_group_id": group_id})

    # Todo 목록 조회
    response = e2e_client.get("/v1/todos")
    assert response.status_code == 200
    todos = response.json()
    assert isinstance(todos, list)
    assert len(todos) >= 3


@pytest.mark.e2e
def test_get_todos_filtered_by_tag_ids_e2e(e2e_client):
    """태그 ID로 필터링된 Todo 목록 조회 E2E 테스트"""
    # 그룹 및 태그 생성
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "업무", "color": "#FF5733"}
    )
    group_id = group_response.json()["id"]

    tag1_response = e2e_client.post(
        "/v1/tags",
        json={"name": "태그1", "color": "#FF0000", "group_id": group_id}
    )
    tag1_id = tag1_response.json()["id"]

    tag2_response = e2e_client.post(
        "/v1/tags",
        json={"name": "태그2", "color": "#00FF00", "group_id": group_id}
    )
    tag2_id = tag2_response.json()["id"]

    # Todo 생성
    todo1_response = e2e_client.post(
        "/v1/todos",
        json={"title": "Todo 1", "tag_group_id": group_id, "tag_ids": [tag1_id]}
    )
    todo1_id = todo1_response.json()["id"]

    todo2_response = e2e_client.post(
        "/v1/todos",
        json={"title": "Todo 2", "tag_group_id": group_id, "tag_ids": [tag2_id]}
    )
    todo2_id = todo2_response.json()["id"]

    todo3_response = e2e_client.post(
        "/v1/todos",
        json={"title": "Todo 3", "tag_group_id": group_id, "tag_ids": [tag1_id, tag2_id]}
    )
    todo3_id = todo3_response.json()["id"]

    e2e_client.post("/v1/todos", json={"title": "Todo 4", "tag_group_id": group_id})  # 태그 없음

    # tag1만 가진 Todo 조회
    response = e2e_client.get("/v1/todos", params={"tag_ids": [tag1_id]})
    assert response.status_code == 200
    todos = response.json()
    todo_ids = [t["id"] for t in todos]
    assert todo1_id in todo_ids
    assert todo3_id in todo_ids  # tag1과 tag2 둘 다 가진 Todo도 포함
    assert todo2_id not in todo_ids


@pytest.mark.e2e
def test_get_todos_filtered_by_group_ids_e2e(e2e_client):
    """그룹 ID로 필터링된 Todo 목록 조회 E2E 테스트"""
    # 그룹 생성
    group1_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "업무", "color": "#FF5733"}
    )
    group1_id = group1_response.json()["id"]

    group2_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "개인", "color": "#0000FF"}
    )
    group2_id = group2_response.json()["id"]

    # 태그 생성
    tag1_response = e2e_client.post(
        "/v1/tags",
        json={"name": "태그1", "color": "#FF0000", "group_id": group1_id}
    )
    tag1_id = tag1_response.json()["id"]

    tag2_response = e2e_client.post(
        "/v1/tags",
        json={"name": "태그2", "color": "#00FF00", "group_id": group2_id}
    )
    tag2_id = tag2_response.json()["id"]

    # Todo 생성
    todo1_response = e2e_client.post(
        "/v1/todos",
        json={"title": "Todo 1", "tag_group_id": group1_id, "tag_ids": [tag1_id]}
    )
    todo1_id = todo1_response.json()["id"]

    todo2_response = e2e_client.post(
        "/v1/todos",
        json={"title": "Todo 2", "tag_group_id": group2_id, "tag_ids": [tag2_id]}
    )
    todo2_id = todo2_response.json()["id"]

    # group1의 태그를 가진 Todo 조회
    response = e2e_client.get("/v1/todos", params={"group_ids": [group1_id]})
    assert response.status_code == 200
    todos = response.json()
    todo_ids = [t["id"] for t in todos]
    assert todo1_id in todo_ids
    assert todo2_id not in todo_ids


@pytest.mark.e2e
def test_update_todo_e2e(e2e_client):
    """HTTP를 통한 Todo 업데이트 E2E 테스트"""
    # 태그 그룹 생성
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "업무", "color": "#FF5733"}
    )
    group_id = group_response.json()["id"]
    
    # Todo 생성
    create_response = e2e_client.post(
        "/v1/todos",
        json={
            "title": "원본 제목",
            "description": "원본 설명",
            "tag_group_id": group_id,
        },
    )
    assert create_response.status_code == 201
    todo_id = create_response.json()["id"]

    # Todo 업데이트
    update_response = e2e_client.patch(
        f"/v1/todos/{todo_id}",
        json={
            "title": "업데이트된 제목",
            "description": "업데이트된 설명",
        },
    )
    assert update_response.status_code == 200
    data = update_response.json()
    assert data["title"] == "업데이트된 제목"
    assert data["description"] == "업데이트된 설명"


@pytest.mark.e2e
def test_update_todo_partial_e2e(e2e_client):
    """Todo 부분 업데이트 E2E 테스트"""
    # 태그 그룹 생성
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "업무", "color": "#FF5733"}
    )
    group_id = group_response.json()["id"]
    
    # Todo 생성
    create_response = e2e_client.post(
        "/v1/todos",
        json={
            "title": "원본 제목",
            "description": "원본 설명",
            "tag_group_id": group_id,
        },
    )
    todo_id = create_response.json()["id"]
    original_title = create_response.json()["title"]

    # 설명만 업데이트
    update_response = e2e_client.patch(
        f"/v1/todos/{todo_id}",
        json={"description": "설명만 업데이트"},
    )
    assert update_response.status_code == 200
    data = update_response.json()
    assert data["title"] == original_title  # 제목은 변경되지 않음
    assert data["description"] == "설명만 업데이트"


@pytest.mark.e2e
def test_update_todo_deadline_e2e(e2e_client):
    """Todo 마감 시간 업데이트 E2E 테스트"""
    # 태그 그룹 생성
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "업무", "color": "#FF5733"}
    )
    group_id = group_response.json()["id"]
    
    # Todo 생성
    create_response = e2e_client.post(
        "/v1/todos",
        json={
            "title": "마감 시간 업데이트 테스트",
            "tag_group_id": group_id,
        },
    )
    todo_id = create_response.json()["id"]

    # 마감 시간 추가
    update_response = e2e_client.patch(
        f"/v1/todos/{todo_id}",
        json={"deadline": "2024-01-15T12:00:00Z"},
    )
    assert update_response.status_code == 200
    data = update_response.json()
    assert data["deadline"] is not None
    assert "2024-01-15T12:00:00" in data["deadline"]
    # Schedule이 생성되었는지 확인
    assert len(data["schedules"]) == 1


@pytest.mark.e2e
def test_update_todo_status_e2e(e2e_client):
    """Todo 상태 업데이트 E2E 테스트"""
    # 태그 그룹 생성
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "업무", "color": "#FF5733"}
    )
    group_id = group_response.json()["id"]
    
    # Todo 생성
    create_response = e2e_client.post(
        "/v1/todos",
        json={
            "title": "상태 업데이트 테스트",
            "tag_group_id": group_id,
        },
    )
    todo_id = create_response.json()["id"]

    # 상태 업데이트
    update_response = e2e_client.patch(
        f"/v1/todos/{todo_id}",
        json={"status": "DONE"},
    )
    assert update_response.status_code == 200
    data = update_response.json()
    assert data["status"] == "DONE"


@pytest.mark.e2e
def test_update_todo_tags_e2e(e2e_client):
    """Todo 태그 업데이트 E2E 테스트"""
    # 태그 그룹 생성
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "업무", "color": "#FF5733"}
    )
    group_id = group_response.json()["id"]
    
    # Todo 생성
    create_response = e2e_client.post(
        "/v1/todos",
        json={
            "title": "태그 업데이트 테스트 Todo",
            "tag_group_id": group_id,
        },
    )
    todo_id = create_response.json()["id"]

    # 태그 생성
    tag1_response = e2e_client.post(
        "/v1/tags",
        json={"name": "태그1", "color": "#FF0000", "group_id": group_id}
    )
    tag1_id = tag1_response.json()["id"]

    tag2_response = e2e_client.post(
        "/v1/tags",
        json={"name": "태그2", "color": "#00FF00", "group_id": group_id}
    )
    tag2_id = tag2_response.json()["id"]

    # Todo 태그 업데이트
    update_response = e2e_client.patch(
        f"/v1/todos/{todo_id}",
        json={"tag_ids": [tag1_id, tag2_id]},
    )
    assert update_response.status_code == 200
    data = update_response.json()

    # 태그 확인
    assert "tags" in data
    tags = data["tags"]
    assert len(tags) == 2
    tag_ids = [t["id"] for t in tags]
    assert tag1_id in tag_ids
    assert tag2_id in tag_ids


@pytest.mark.e2e
def test_update_todo_remove_tags_e2e(e2e_client):
    """Todo 태그 제거 E2E 테스트"""
    # 태그 그룹 생성
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "업무", "color": "#FF5733"}
    )
    group_id = group_response.json()["id"]

    # 태그 생성
    tag_response = e2e_client.post(
        "/v1/tags",
        json={"name": "중요", "color": "#FF0000", "group_id": group_id}
    )
    tag_id = tag_response.json()["id"]

    # 태그와 함께 Todo 생성
    create_response = e2e_client.post(
        "/v1/todos",
        json={
            "title": "태그 있는 Todo",
            "tag_group_id": group_id,
            "tag_ids": [tag_id],
        },
    )
    todo_id = create_response.json()["id"]

    # 태그 제거
    update_response = e2e_client.patch(
        f"/v1/todos/{todo_id}",
        json={"tag_ids": []},
    )
    assert update_response.status_code == 200
    data = update_response.json()

    # 태그가 제거되었는지 확인
    assert "tags" in data
    assert len(data["tags"]) == 0


@pytest.mark.e2e
def test_update_todo_not_found_e2e(e2e_client):
    """존재하지 않는 Todo 업데이트 실패 E2E 테스트"""
    non_existent_id = str(uuid4())
    response = e2e_client.patch(
        f"/v1/todos/{non_existent_id}",
        json={"title": "업데이트"},
    )

    assert response.status_code == 404


@pytest.mark.e2e
def test_delete_todo_e2e(e2e_client):
    """HTTP를 통한 Todo 삭제 E2E 테스트"""
    # 태그 그룹 생성
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "업무", "color": "#FF5733"}
    )
    group_id = group_response.json()["id"]
    
    # Todo 생성
    create_response = e2e_client.post(
        "/v1/todos",
        json={
            "title": "삭제 테스트 Todo",
            "tag_group_id": group_id,
        },
    )
    todo_id = create_response.json()["id"]

    # Todo 삭제
    delete_response = e2e_client.delete(f"/v1/todos/{todo_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["ok"] is True

    # 삭제 확인
    get_response = e2e_client.get(f"/v1/todos/{todo_id}")
    assert get_response.status_code == 404


@pytest.mark.e2e
def test_delete_todo_with_schedule_e2e(e2e_client):
    """Schedule이 연관된 Todo 삭제 E2E 테스트"""
    # 태그 그룹 생성
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "업무", "color": "#FF5733"}
    )
    group_id = group_response.json()["id"]
    
    # 마감 시간이 있는 Todo 생성 (Schedule 자동 생성)
    create_response = e2e_client.post(
        "/v1/todos",
        json={
            "title": "Schedule 있는 Todo",
            "tag_group_id": group_id,
            "deadline": "2024-01-01T12:00:00Z",
        },
    )
    todo_id = create_response.json()["id"]
    schedule_id = create_response.json()["schedules"][0]["id"]

    # Todo 삭제
    delete_response = e2e_client.delete(f"/v1/todos/{todo_id}")
    assert delete_response.status_code == 200

    # Todo가 삭제되었는지 확인
    get_todo_response = e2e_client.get(f"/v1/todos/{todo_id}")
    assert get_todo_response.status_code == 404

    # Schedule도 삭제되었는지 확인
    get_schedule_response = e2e_client.get(f"/v1/schedules/{schedule_id}")
    assert get_schedule_response.status_code == 404


@pytest.mark.e2e
def test_delete_todo_not_found_e2e(e2e_client):
    """존재하지 않는 Todo 삭제 실패 E2E 테스트"""
    non_existent_id = str(uuid4())
    response = e2e_client.delete(f"/v1/todos/{non_existent_id}")

    assert response.status_code == 404


@pytest.mark.e2e
def test_get_todo_stats_e2e(e2e_client):
    """HTTP를 통한 Todo 통계 조회 E2E 테스트"""
    # 그룹 및 태그 생성
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "업무", "color": "#FF5733"}
    )
    group_id = group_response.json()["id"]

    tag1_response = e2e_client.post(
        "/v1/tags",
        json={"name": "태그1", "color": "#FF0000", "group_id": group_id}
    )
    tag1_id = tag1_response.json()["id"]

    tag2_response = e2e_client.post(
        "/v1/tags",
        json={"name": "태그2", "color": "#00FF00", "group_id": group_id}
    )
    tag2_id = tag2_response.json()["id"]

    # Todo 생성
    e2e_client.post("/v1/todos", json={"title": "Todo 1", "tag_group_id": group_id, "tag_ids": [tag1_id]})
    e2e_client.post("/v1/todos", json={"title": "Todo 2", "tag_group_id": group_id, "tag_ids": [tag1_id]})
    e2e_client.post("/v1/todos", json={"title": "Todo 3", "tag_group_id": group_id, "tag_ids": [tag2_id]})
    e2e_client.post("/v1/todos", json={"title": "Todo 4", "tag_group_id": group_id})  # 태그 없음

    # 통계 조회
    response = e2e_client.get("/v1/todos/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_count" in data
    assert "by_tag" in data
    assert data["total_count"] >= 4
    assert len(data["by_tag"]) >= 2


@pytest.mark.e2e
def test_get_todo_stats_filtered_by_group_e2e(e2e_client):
    """그룹별 Todo 통계 조회 E2E 테스트"""
    # 그룹 생성
    group1_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "업무", "color": "#FF5733"}
    )
    group1_id = group1_response.json()["id"]

    group2_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "개인", "color": "#0000FF"}
    )
    group2_id = group2_response.json()["id"]

    # 태그 생성
    tag1_response = e2e_client.post(
        "/v1/tags",
        json={"name": "태그1", "color": "#FF0000", "group_id": group1_id}
    )
    tag1_id = tag1_response.json()["id"]

    tag2_response = e2e_client.post(
        "/v1/tags",
        json={"name": "태그2", "color": "#00FF00", "group_id": group2_id}
    )
    tag2_id = tag2_response.json()["id"]

    # Todo 생성
    e2e_client.post("/v1/todos", json={"title": "Todo 1", "tag_group_id": group1_id, "tag_ids": [tag1_id]})
    e2e_client.post("/v1/todos", json={"title": "Todo 2", "tag_group_id": group2_id, "tag_ids": [tag2_id]})

    # group1의 통계만 조회
    response = e2e_client.get("/v1/todos/stats", params={"group_id": group1_id})
    assert response.status_code == 200
    data = response.json()
    assert data["group_id"] == group1_id
    assert data["total_count"] >= 1
    assert len(data["by_tag"]) >= 1
    assert data["by_tag"][0]["tag_id"] == tag1_id


@pytest.mark.e2e
def test_todo_workflow_e2e(e2e_client):
    """Todo 전체 워크플로우 E2E 테스트"""
    # 태그 그룹 생성
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "업무", "color": "#FF5733"}
    )
    group_id = group_response.json()["id"]
    
    # 1. Todo 생성
    create_response = e2e_client.post(
        "/v1/todos",
        json={
            "title": "워크플로우 Todo",
            "description": "워크플로우 테스트",
            "tag_group_id": group_id,
        },
    )
    assert create_response.status_code == 201
    todo_id = create_response.json()["id"]

    # 2. Todo 조회
    get_response = e2e_client.get(f"/v1/todos/{todo_id}")
    assert get_response.status_code == 200
    assert get_response.json()["title"] == "워크플로우 Todo"

    # 3. Todo 업데이트
    update_response = e2e_client.patch(
        f"/v1/todos/{todo_id}",
        json={"title": "업데이트된 Todo"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["title"] == "업데이트된 Todo"

    # 4. Todo 삭제
    delete_response = e2e_client.delete(f"/v1/todos/{todo_id}")
    assert delete_response.status_code == 200

    # 5. 삭제 확인
    get_response = e2e_client.get(f"/v1/todos/{todo_id}")
    assert get_response.status_code == 404


@pytest.mark.e2e
def test_todo_with_tags_workflow_e2e(e2e_client):
    """태그가 있는 Todo 전체 워크플로우 E2E 테스트"""
    # 1. 그룹 및 태그 생성
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "업무", "color": "#FF5733"}
    )
    group_id = group_response.json()["id"]

    tag1_response = e2e_client.post(
        "/v1/tags",
        json={"name": "태그1", "color": "#FF0000", "group_id": group_id}
    )
    tag1_id = tag1_response.json()["id"]

    tag2_response = e2e_client.post(
        "/v1/tags",
        json={"name": "태그2", "color": "#00FF00", "group_id": group_id}
    )
    tag2_id = tag2_response.json()["id"]

    # 2. 태그와 함께 Todo 생성
    create_response = e2e_client.post(
        "/v1/todos",
        json={
            "title": "태그 워크플로우 Todo",
            "tag_group_id": group_id,
            "tag_ids": [tag1_id],
        },
    )
    assert create_response.status_code == 201
    todo_id = create_response.json()["id"]
    assert len(create_response.json()["tags"]) == 1

    # 3. Todo 태그 업데이트
    update_response = e2e_client.patch(
        f"/v1/todos/{todo_id}",
        json={"tag_ids": [tag1_id, tag2_id]},
    )
    assert update_response.status_code == 200
    assert len(update_response.json()["tags"]) == 2

    # 4. Todo 조회 시 태그 확인
    get_response = e2e_client.get(f"/v1/todos/{todo_id}")
    assert get_response.status_code == 200
    tags = get_response.json()["tags"]
    assert len(tags) == 2
    tag_ids = [t["id"] for t in tags]
    assert tag1_id in tag_ids
    assert tag2_id in tag_ids

    # 5. 태그 필터링으로 Todo 조회
    filtered_response = e2e_client.get("/v1/todos", params={"tag_ids": [tag1_id]})
    assert filtered_response.status_code == 200
    todos = filtered_response.json()
    todo_ids = [t["id"] for t in todos]
    assert todo_id in todo_ids


# ============================================================
# Todo 트리 무결성 E2E 테스트
# ============================================================

@pytest.mark.e2e
def test_create_todo_with_invalid_parent_e2e(e2e_client):
    """존재하지 않는 부모 Todo 참조 시 실패 E2E 테스트"""
    # 태그 그룹 생성
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "업무", "color": "#FF5733"}
    )
    group_id = group_response.json()["id"]
    
    # 존재하지 않는 parent_id로 생성 시도
    fake_parent_id = str(uuid4())
    response = e2e_client.post(
        "/v1/todos",
        json={
            "title": "자식 Todo",
            "tag_group_id": group_id,
            "parent_id": fake_parent_id,
        },
    )
    
    assert response.status_code == 400
    assert "parent" in response.json()["message"].lower()


@pytest.mark.e2e
def test_update_todo_self_reference_e2e(e2e_client):
    """자기 자신을 부모로 설정 시 실패 E2E 테스트"""
    # 태그 그룹 생성
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "업무", "color": "#FF5733"}
    )
    group_id = group_response.json()["id"]
    
    # Todo 생성
    create_response = e2e_client.post(
        "/v1/todos",
        json={"title": "자기참조 테스트", "tag_group_id": group_id},
    )
    todo_id = create_response.json()["id"]
    
    # 자기 자신을 부모로 설정 시도
    response = e2e_client.patch(
        f"/v1/todos/{todo_id}",
        json={"parent_id": todo_id},
    )
    
    assert response.status_code == 400
    assert "own parent" in response.json()["message"].lower()


@pytest.mark.e2e
def test_update_todo_creates_cycle_e2e(e2e_client):
    """순환 참조 생성 시 실패 E2E 테스트"""
    # 태그 그룹 생성
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "업무", "color": "#FF5733"}
    )
    group_id = group_response.json()["id"]
    
    # A 생성
    a_response = e2e_client.post(
        "/v1/todos",
        json={"title": "Todo A", "tag_group_id": group_id},
    )
    todo_a_id = a_response.json()["id"]
    
    # B 생성 (부모: A)
    b_response = e2e_client.post(
        "/v1/todos",
        json={"title": "Todo B", "tag_group_id": group_id, "parent_id": todo_a_id},
    )
    todo_b_id = b_response.json()["id"]
    
    # A의 부모를 B로 설정 시도 → cycle
    response = e2e_client.patch(
        f"/v1/todos/{todo_a_id}",
        json={"parent_id": todo_b_id},
    )
    
    assert response.status_code == 400
    assert "cycle" in response.json()["message"].lower()


@pytest.mark.e2e
def test_create_todo_parent_group_mismatch_e2e(e2e_client):
    """부모와 자식의 그룹이 다를 때 실패 E2E 테스트"""
    # 그룹 2개 생성
    group1_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "그룹1", "color": "#FF5733"}
    )
    group1_id = group1_response.json()["id"]
    
    group2_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "그룹2", "color": "#0000FF"}
    )
    group2_id = group2_response.json()["id"]
    
    # 부모 Todo (그룹1)
    parent_response = e2e_client.post(
        "/v1/todos",
        json={"title": "부모 Todo", "tag_group_id": group1_id},
    )
    parent_id = parent_response.json()["id"]
    
    # 다른 그룹의 자식 Todo 생성 시도
    response = e2e_client.post(
        "/v1/todos",
        json={
            "title": "자식 Todo",
            "tag_group_id": group2_id,
            "parent_id": parent_id,
        },
    )
    
    assert response.status_code == 400
    assert "group" in response.json()["message"].lower()


# ============================================================
# Todo 조상 포함 E2E 테스트
# ============================================================

@pytest.mark.e2e
def test_get_todos_includes_ancestors_with_tag_filter_e2e(e2e_client):
    """태그 필터 시 조상 노드도 포함되는지 E2E 테스트"""
    # 그룹 생성
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "업무", "color": "#FF5733"}
    )
    group_id = group_response.json()["id"]
    
    # 태그 생성
    tag_response = e2e_client.post(
        "/v1/tags",
        json={"name": "조상포함테스트", "color": "#FF0000", "group_id": group_id}
    )
    tag_id = tag_response.json()["id"]
    
    # 부모 Todo (태그 없음)
    parent_response = e2e_client.post(
        "/v1/todos",
        json={"title": "부모 (태그 없음)", "tag_group_id": group_id},
    )
    parent_id = parent_response.json()["id"]
    
    # 자식 Todo (태그 있음)
    child_response = e2e_client.post(
        "/v1/todos",
        json={
            "title": "자식 (태그 있음)",
            "tag_group_id": group_id,
            "parent_id": parent_id,
            "tag_ids": [tag_id],
        },
    )
    child_id = child_response.json()["id"]
    
    # 태그로 필터링
    response = e2e_client.get("/v1/todos", params={"tag_ids": [tag_id]})
    assert response.status_code == 200
    
    todos = response.json()
    todo_ids = [t["id"] for t in todos]
    
    # 자식은 태그 매칭으로 포함
    assert child_id in todo_ids, "자식 Todo가 결과에 포함되어야 함"
    # 부모는 조상으로 포함
    assert parent_id in todo_ids, "부모 Todo가 조상으로 포함되어야 함"
