import pytest
from datetime import datetime, UTC
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    """테스트용 FastAPI 클라이언트"""
    return TestClient(app)


@pytest.mark.e2e
def test_create_schedule_e2e(client):
    """HTTP를 통한 일정 생성 E2E 테스트"""
    response = client.post(
        "/schedules",
        json={
            "title": "E2E 테스트 일정",
            "description": "E2E 테스트 설명",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "E2E 테스트 일정"
    assert data["description"] == "E2E 테스트 설명"
    assert "id" in data
    assert "created_at" in data


@pytest.mark.e2e
def test_get_schedule_e2e(client):
    """HTTP를 통한 일정 조회 E2E 테스트"""
    # 1. 일정 생성
    create_response = client.post(
        "/schedules",
        json={
            "title": "조회 테스트 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    assert create_response.status_code == 200
    schedule_id = create_response.json()["id"]
    
    # 2. 일정 조회
    get_response = client.get(f"/schedules/{schedule_id}")
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["id"] == schedule_id
    assert data["title"] == "조회 테스트 일정"


@pytest.mark.e2e
def test_get_schedule_not_found_e2e(client):
    """존재하지 않는 일정 조회 E2E 테스트"""
    from uuid import uuid4
    
    non_existent_id = str(uuid4())
    response = client.get(f"/schedules/{non_existent_id}")
    
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.e2e
def test_get_all_schedules_e2e(client):
    """HTTP를 통한 모든 일정 조회 E2E 테스트"""
    # 1. 여러 일정 생성
    for i in range(3):
        client.post(
            "/schedules",
            json={
                "title": f"일정 {i}",
                "start_time": f"2024-01-01T{10+i:02d}:00:00Z",
                "end_time": f"2024-01-01T{12+i:02d}:00:00Z",
            },
        )
    
    # 2. 모든 일정 조회
    response = client.get("/schedules")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 3


@pytest.mark.e2e
def test_update_schedule_e2e(client):
    """HTTP를 통한 일정 업데이트 E2E 테스트"""
    # 1. 일정 생성
    create_response = client.post(
        "/schedules",
        json={
            "title": "원본 제목",
            "description": "원본 설명",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    assert create_response.status_code == 200
    schedule_id = create_response.json()["id"]
    
    # 2. 일정 업데이트
    update_response = client.patch(
        f"/schedules/{schedule_id}",
        json={
            "title": "업데이트된 제목",
            "description": "업데이트된 설명",
        },
    )
    assert update_response.status_code == 200
    updated_data = update_response.json()
    assert updated_data["title"] == "업데이트된 제목"
    assert updated_data["description"] == "업데이트된 설명"
    
    # 3. 업데이트 확인
    get_response = client.get(f"/schedules/{schedule_id}")
    assert get_response.status_code == 200
    assert get_response.json()["title"] == "업데이트된 제목"


@pytest.mark.e2e
def test_delete_schedule_e2e(client):
    """HTTP를 통한 일정 삭제 E2E 테스트"""
    # 1. 일정 생성
    create_response = client.post(
        "/schedules",
        json={
            "title": "삭제 테스트 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    assert create_response.status_code == 200
    schedule_id = create_response.json()["id"]
    
    # 2. 일정 삭제
    delete_response = client.delete(f"/schedules/{schedule_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["ok"] is True
    
    # 3. 삭제 확인
    get_response = client.get(f"/schedules/{schedule_id}")
    assert get_response.status_code == 404


@pytest.mark.e2e
def test_schedule_flow_e2e(client):
    """HTTP를 통한 일정 전체 흐름 E2E 테스트"""
    # 1. 일정 생성
    create_response = client.post(
        "/schedules",
        json={
            "title": "전체 흐름 테스트",
            "description": "초기 설명",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    assert create_response.status_code == 200
    schedule_data = create_response.json()
    schedule_id = schedule_data["id"]
    assert schedule_data["title"] == "전체 흐름 테스트"
    
    # 2. 일정 조회
    get_response = client.get(f"/schedules/{schedule_id}")
    assert get_response.status_code == 200
    assert get_response.json()["title"] == "전체 흐름 테스트"
    
    # 3. 일정 업데이트
    update_response = client.patch(
        f"/schedules/{schedule_id}",
        json={
            "title": "업데이트된 전체 흐름",
            "description": "업데이트된 설명",
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["title"] == "업데이트된 전체 흐름"
    
    # 4. 최종 상태 확인
    final_response = client.get(f"/schedules/{schedule_id}")
    assert final_response.status_code == 200
    final_data = final_response.json()
    assert final_data["title"] == "업데이트된 전체 흐름"
    assert final_data["description"] == "업데이트된 설명"
    
    # 5. 일정 삭제
    delete_response = client.delete(f"/schedules/{schedule_id}")
    assert delete_response.status_code == 200
    
    # 6. 삭제 확인
    deleted_response = client.get(f"/schedules/{schedule_id}")
    assert deleted_response.status_code == 404


@pytest.mark.e2e
def test_create_schedule_invalid_time_e2e(client):
    """잘못된 시간으로 일정 생성 실패 E2E 테스트"""
    response = client.post(
        "/schedules",
        json={
            "title": "잘못된 시간 테스트",
            "start_time": "2024-01-01T12:00:00Z",
            "end_time": "2024-01-01T10:00:00Z",  # end_time < start_time
        },
    )
    
    # Pydantic validation이 실패해야 함
    assert response.status_code == 422

