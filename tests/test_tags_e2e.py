"""
Tag E2E Tests
"""
from uuid import uuid4

import pytest


@pytest.mark.e2e
def test_create_tag_group_e2e(e2e_client):
    """태그 그룹 생성 E2E"""
    response = e2e_client.post(
        "/v1/tags/groups",
        json={
            "name": "업무",
            "color": "#FF5733",
            "description": "업무 관련 태그",
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "업무"
    assert data["color"] == "#FF5733"
    assert "id" in data


@pytest.mark.e2e
def test_get_tag_group_e2e(e2e_client):
    """태그 그룹 조회 E2E"""
    # 그룹 생성
    create_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "업무", "color": "#FF5733"}
    )
    group_id = create_response.json()["id"]

    # 조회
    response = e2e_client.get(f"/v1/tags/groups/{group_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == group_id
    assert data["name"] == "업무"


@pytest.mark.e2e
def test_get_tag_group_not_found_e2e(e2e_client):
    """태그 그룹 조회 실패 E2E"""
    fake_id = str(uuid4())
    response = e2e_client.get(f"/v1/tags/groups/{fake_id}")
    assert response.status_code == 404


@pytest.mark.e2e
def test_create_tag_e2e(e2e_client):
    """태그 생성 E2E"""
    # 그룹 생성
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "업무", "color": "#FF5733"}
    )
    group_id = group_response.json()["id"]

    # 태그 생성
    response = e2e_client.post(
        "/v1/tags",
        json={
            "name": "중요",
            "color": "#FF0000",
            "group_id": group_id,
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "중요"
    assert data["group_id"] == group_id


@pytest.mark.e2e
def test_create_schedule_with_tags_e2e(e2e_client):
    """일정 생성 시 태그 함께 설정 E2E"""
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

    # 일정 생성 시 태그 함께 설정
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "회의",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
            "tag_ids": [tag_id],
        }
    )
    assert schedule_response.status_code == 201
    schedule_data = schedule_response.json()
    schedule_id = schedule_data["id"]

    # 일정의 태그 확인
    assert "tags" in schedule_data
    tags = schedule_data["tags"]
    assert len(tags) == 1
    assert tags[0]["id"] == tag_id


@pytest.mark.e2e
def test_update_schedule_tags_e2e(e2e_client):
    """일정 수정 시 태그 업데이트 E2E"""
    # 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "회의",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        }
    )
    schedule_id = schedule_response.json()["id"]

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

    # 일정 수정 시 태그 업데이트
    update_response = e2e_client.patch(
        f"/v1/schedules/{schedule_id}",
        json={"tag_ids": [tag1_id, tag2_id]}
    )
    assert update_response.status_code == 200
    schedule_data = update_response.json()

    # 일정의 태그 확인
    assert "tags" in schedule_data
    tags = schedule_data["tags"]
    assert len(tags) == 2
    tag_ids = [t["id"] for t in tags]
    assert tag1_id in tag_ids
    assert tag2_id in tag_ids


@pytest.mark.e2e
def test_tag_color_validation_e2e(e2e_client):
    """태그 색상 검증 E2E"""
    # 잘못된 색상 형식
    response = e2e_client.post(
        "/v1/tags/groups",
        json={
            "name": "업무",
            "color": "FF5733",  # # 없음
        }
    )
    assert response.status_code == 422  # Validation Error


@pytest.mark.e2e
def test_tag_duplicate_name_in_group_e2e(e2e_client):
    """그룹 내 태그 이름 중복 E2E"""
    # 그룹 생성
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "업무", "color": "#FF5733"}
    )
    group_id = group_response.json()["id"]

    # 첫 번째 태그 생성
    e2e_client.post(
        "/v1/tags",
        json={"name": "중요", "color": "#FF0000", "group_id": group_id}
    )

    # 같은 이름의 태그 생성 시도
    response = e2e_client.post(
        "/v1/tags",
        json={"name": "중요", "color": "#00FF00", "group_id": group_id}
    )
    assert response.status_code == 409  # Conflict


@pytest.mark.e2e
def test_delete_all_tags_deletes_group_e2e(e2e_client):
    """모든 태그 삭제 시 그룹도 자동 삭제 E2E (반복 일정 패턴과 동일)"""
    # 그룹 생성
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "업무", "color": "#FF5733"}
    )
    group_id = group_response.json()["id"]

    # 태그 여러 개 생성
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

    # 첫 번째 태그 삭제 (그룹은 아직 남아있어야 함)
    e2e_client.delete(f"/v1/tags/{tag1_id}")

    # 그룹이 아직 존재하는지 확인
    group_check = e2e_client.get(f"/v1/tags/groups/{group_id}")
    assert group_check.status_code == 200

    # 남은 태그 확인
    tags_response = e2e_client.get("/v1/tags")
    tags = tags_response.json()
    remaining_tags = [t for t in tags if t["group_id"] == group_id]
    assert len(remaining_tags) == 1  # tag2만 남음

    # 마지막 태그 삭제 (그룹도 자동 삭제되어야 함)
    e2e_client.delete(f"/v1/tags/{tag2_id}")

    # 그룹이 자동으로 삭제되었는지 확인
    group_check = e2e_client.get(f"/v1/tags/groups/{group_id}")
    assert group_check.status_code == 404  # 그룹이 삭제됨


@pytest.mark.e2e
def test_delete_tag_keeps_group_with_remaining_tags_e2e(e2e_client):
    """태그 삭제 시 다른 태그가 남아있으면 그룹 유지 E2E"""
    # 그룹 생성
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "업무", "color": "#FF5733"}
    )
    group_id = group_response.json()["id"]

    # 태그 여러 개 생성
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

    # 하나의 태그만 삭제
    e2e_client.delete(f"/v1/tags/{tag1_id}")

    # 그룹이 여전히 존재하는지 확인
    group_check = e2e_client.get(f"/v1/tags/groups/{group_id}")
    assert group_check.status_code == 200

    # 남은 태그 확인
    tags_response = e2e_client.get("/v1/tags")
    tags = tags_response.json()
    remaining_tags = [t for t in tags if t["group_id"] == group_id]
    assert len(remaining_tags) == 1  # tag2가 남아있음
