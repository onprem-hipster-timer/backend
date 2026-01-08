"""
Todo E2E Tests

HTTP API를 통한 Todo E2E 테스트
"""
from uuid import uuid4

import pytest


@pytest.mark.e2e
def test_create_todo_e2e(e2e_client):
    """HTTP를 통한 Todo 생성 E2E 테스트"""
    response = e2e_client.post(
        "/v1/todos",
        json={
            "title": "E2E 테스트 Todo",
            "description": "E2E 테스트 설명",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "E2E 테스트 Todo"
    assert data["description"] == "E2E 테스트 설명"
    assert data["is_todo"] is True
    assert "id" in data
    assert "start_time" in data
    assert "end_time" in data
    assert "tags" in data


@pytest.mark.e2e
def test_create_todo_with_deadline_e2e(e2e_client):
    """마감 시간이 있는 Todo 생성 E2E 테스트"""
    response = e2e_client.post(
        "/v1/todos",
        json={
            "title": "마감 시간 있는 Todo",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "마감 시간 있는 Todo"
    assert "2024-01-01T10:00:00" in data["start_time"]
    assert "2024-01-01T12:00:00" in data["end_time"]


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
def test_get_todo_e2e(e2e_client):
    """HTTP를 통한 Todo 조회 E2E 테스트"""
    # Todo 생성
    create_response = e2e_client.post(
        "/v1/todos",
        json={
            "title": "조회 테스트 Todo",
            "description": "조회 테스트 설명",
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
    assert data["is_todo"] is True


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
    # 여러 Todo 생성
    e2e_client.post("/v1/todos", json={"title": "Todo 1"})
    e2e_client.post("/v1/todos", json={"title": "Todo 2"})
    e2e_client.post("/v1/todos", json={"title": "Todo 3"})

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
        json={"title": "Todo 1", "tag_ids": [tag1_id]}
    )
    todo1_id = todo1_response.json()["id"]

    todo2_response = e2e_client.post(
        "/v1/todos",
        json={"title": "Todo 2", "tag_ids": [tag2_id]}
    )
    todo2_id = todo2_response.json()["id"]

    todo3_response = e2e_client.post(
        "/v1/todos",
        json={"title": "Todo 3", "tag_ids": [tag1_id, tag2_id]}
    )
    todo3_id = todo3_response.json()["id"]

    e2e_client.post("/v1/todos", json={"title": "Todo 4"})  # 태그 없음

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
        json={"title": "Todo 1", "tag_ids": [tag1_id]}
    )
    todo1_id = todo1_response.json()["id"]

    todo2_response = e2e_client.post(
        "/v1/todos",
        json={"title": "Todo 2", "tag_ids": [tag2_id]}
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
    # Todo 생성
    create_response = e2e_client.post(
        "/v1/todos",
        json={
            "title": "원본 제목",
            "description": "원본 설명",
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
    # Todo 생성
    create_response = e2e_client.post(
        "/v1/todos",
        json={
            "title": "원본 제목",
            "description": "원본 설명",
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
def test_update_todo_tags_e2e(e2e_client):
    """Todo 태그 업데이트 E2E 테스트"""
    # Todo 생성
    create_response = e2e_client.post(
        "/v1/todos",
        json={"title": "태그 업데이트 테스트 Todo"},
    )
    todo_id = create_response.json()["id"]

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
    # 그룹 및 태그 생성
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "업무", "color": "#FF5733"}
    )
    group_id = group_response.json()["id"]

    tag_response = e2e_client.post(
        "/v1/tags",
        json={"name": "중요", "color": "#FF0000", "group_id": group_id}
    )
    tag_id = tag_response.json()["id"]

    # 태그와 함께 Todo 생성
    create_response = e2e_client.post(
        "/v1/todos",
        json={"title": "태그 있는 Todo", "tag_ids": [tag_id]},
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
    # Todo 생성
    create_response = e2e_client.post(
        "/v1/todos",
        json={"title": "삭제 테스트 Todo"},
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
    e2e_client.post("/v1/todos", json={"title": "Todo 1", "tag_ids": [tag1_id]})
    e2e_client.post("/v1/todos", json={"title": "Todo 2", "tag_ids": [tag1_id]})
    e2e_client.post("/v1/todos", json={"title": "Todo 3", "tag_ids": [tag2_id]})
    e2e_client.post("/v1/todos", json={"title": "Todo 4"})  # 태그 없음

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
    e2e_client.post("/v1/todos", json={"title": "Todo 1", "tag_ids": [tag1_id]})
    e2e_client.post("/v1/todos", json={"title": "Todo 2", "tag_ids": [tag2_id]})

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
    # 1. Todo 생성
    create_response = e2e_client.post(
        "/v1/todos",
        json={
            "title": "워크플로우 Todo",
            "description": "워크플로우 테스트",
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
        json={"title": "태그 워크플로우 Todo", "tag_ids": [tag1_id]},
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


@pytest.mark.e2e
def test_convert_todo_with_deadline_to_schedule_e2e(e2e_client):
    """마감 시간이 있는 Todo를 일정으로 변환 E2E 테스트"""
    # 1. 마감 시간이 있는 Todo 생성
    todo_response = e2e_client.post(
        "/v1/todos",
        json={
            "title": "마감 시간 있는 Todo",
            "start_time": "2024-01-20T10:00:00Z",
            "end_time": "2024-01-20T12:00:00Z",
        },
    )
    assert todo_response.status_code == 201
    todo_id = todo_response.json()["id"]
    assert todo_response.json()["is_todo"] is True

    # 2. Todo를 일정으로 변환
    convert_response = e2e_client.patch(
        f"/v1/todos/{todo_id}",
        json={"is_todo": False},
    )
    assert convert_response.status_code == 200
    schedule = convert_response.json()
    assert schedule["is_todo"] is False
    assert schedule["title"] == "마감 시간 있는 Todo"
    assert "2024-01-20T10:00:00" in schedule["start_time"]
    assert "2024-01-20T12:00:00" in schedule["end_time"]

    # 3. 일정 목록에서 확인
    schedules_response = e2e_client.get(
        "/v1/schedules",
        params={
            "start_date": "2024-01-01T00:00:00Z",
            "end_date": "2024-01-31T23:59:59Z"
        }
    )
    assert schedules_response.status_code == 200
    schedules = schedules_response.json()
    schedule_ids = [s["id"] for s in schedules]
    assert todo_id in schedule_ids


@pytest.mark.e2e
def test_convert_todo_without_deadline_to_schedule_e2e(e2e_client):
    """마감 시간이 없는 Todo를 일정으로 변환 E2E 테스트"""
    # 1. 마감 시간이 없는 Todo 생성
    todo_response = e2e_client.post(
        "/v1/todos",
        json={"title": "마감 시간 없는 Todo"},
    )
    assert todo_response.status_code == 201
    todo_id = todo_response.json()["id"]
    assert todo_response.json()["is_todo"] is True

    # 2. 마감 시간과 함께 Todo를 일정으로 변환
    convert_response = e2e_client.patch(
        f"/v1/todos/{todo_id}",
        json={
            "is_todo": False,
            "start_time": "2024-01-20T10:00:00Z",
            "end_time": "2024-01-20T12:00:00Z",
        },
    )
    assert convert_response.status_code == 200
    schedule = convert_response.json()
    assert schedule["is_todo"] is False
    assert schedule["title"] == "마감 시간 없는 Todo"
    assert "2024-01-20T10:00:00" in schedule["start_time"]
    assert "2024-01-20T12:00:00" in schedule["end_time"]


@pytest.mark.e2e
def test_convert_todo_without_deadline_to_schedule_fails_e2e(e2e_client):
    """마감 시간이 없는 Todo를 마감 시간 없이 일정으로 변환 실패 E2E 테스트"""
    # 1. 마감 시간이 없는 Todo 생성
    todo_response = e2e_client.post(
        "/v1/todos",
        json={"title": "마감 시간 없는 Todo"},
    )
    assert todo_response.status_code == 201
    todo_id = todo_response.json()["id"]

    # 2. 마감 시간 없이 Todo를 일정으로 변환 시도 (실패해야 함)
    convert_response = e2e_client.patch(
        f"/v1/todos/{todo_id}",
        json={"is_todo": False},
    )
    assert convert_response.status_code == 400
    error = convert_response.json()
    assert error["error_type"] == "DeadlineRequiredForConversionError"


@pytest.mark.e2e
def test_convert_schedule_to_todo_e2e(e2e_client):
    """일정을 Todo로 변환 E2E 테스트"""
    # 1. 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "일정",
            "start_time": "2024-01-15T10:00:00Z",
            "end_time": "2024-01-15T12:00:00Z",
        },
    )
    assert schedule_response.status_code == 201
    schedule_id = schedule_response.json()["id"]
    assert schedule_response.json()["is_todo"] is False

    # 2. 일정을 Todo로 변환
    convert_response = e2e_client.patch(
        f"/v1/schedules/{schedule_id}",
        json={"is_todo": True},
    )
    assert convert_response.status_code == 200
    todo = convert_response.json()
    assert todo["is_todo"] is True
    assert todo["title"] == "일정"
    assert "2024-01-15T10:00:00" in todo["start_time"]
    assert "2024-01-15T12:00:00" in todo["end_time"]

    # 3. Todo 목록에서 확인
    todos_response = e2e_client.get("/v1/todos")
    assert todos_response.status_code == 200
    todos = todos_response.json()
    todo_ids = [t["id"] for t in todos]
    assert schedule_id in todo_ids
