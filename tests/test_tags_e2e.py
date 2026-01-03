"""
Tag E2E Tests
"""
import pytest
from uuid import uuid4

from app.domain.schedule.schema.dto import ScheduleCreate
from datetime import datetime, UTC


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
def test_add_tag_to_schedule_e2e(e2e_client):
    """일정에 태그 추가 E2E"""
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
    
    tag_response = e2e_client.post(
        "/v1/tags",
        json={
            "name": "중요",
            "color": "#FF0000",
            "group_id": group_id,
        }
    )
    tag_id = tag_response.json()["id"]
    
    # 일정에 태그 추가
    response = e2e_client.post(
        f"/v1/tags/schedules/{schedule_id}/tags/{tag_id}"
    )
    assert response.status_code == 201
    
    # 일정의 태그 조회
    tags_response = e2e_client.get(f"/v1/tags/schedules/{schedule_id}/tags")
    assert tags_response.status_code == 200
    tags = tags_response.json()
    assert len(tags) == 1
    assert tags[0]["id"] == tag_id


@pytest.mark.e2e
def test_set_schedule_tags_e2e(e2e_client):
    """일정의 태그 일괄 설정 E2E"""
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
    
    # 태그 일괄 설정
    response = e2e_client.put(
        f"/v1/tags/schedules/{schedule_id}/tags",
        json=[tag1_id, tag2_id]
    )
    assert response.status_code == 200
    tags = response.json()
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

