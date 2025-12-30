"""
Timer E2E Tests

HTTP API를 통한 타이머 E2E 테스트
"""
import pytest
from datetime import datetime, UTC
from uuid import uuid4


@pytest.mark.e2e
def test_create_timer_e2e(e2e_client):
    """HTTP를 통한 타이머 생성 E2E 테스트"""
    # 1. 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "타이머 테스트 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    assert schedule_response.status_code == 201
    schedule_id = schedule_response.json()["id"]
    
    # 2. 타이머 생성
    timer_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "title": "E2E 테스트 타이머",
            "description": "E2E 테스트 설명",
            "allocated_duration": 1800,
        },
    )
    
    assert timer_response.status_code == 201
    data = timer_response.json()
    assert data["title"] == "E2E 테스트 타이머"
    assert data["description"] == "E2E 테스트 설명"
    assert data["allocated_duration"] == 1800
    assert data["elapsed_time"] == 0
    assert data["status"] == "running"
    assert "id" in data
    assert "schedule" in data
    assert data["schedule"]["id"] == schedule_id


@pytest.mark.e2e
def test_get_timer_e2e(e2e_client):
    """HTTP를 통한 타이머 조회 E2E 테스트"""
    # 1. 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "조회 테스트 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]
    
    # 2. 타이머 생성
    create_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "title": "조회 테스트 타이머",
            "allocated_duration": 1800,
        },
    )
    assert create_response.status_code == 201
    timer_id = create_response.json()["id"]
    
    # 3. 타이머 조회
    get_response = e2e_client.get(f"/v1/timers/{timer_id}")
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["id"] == timer_id
    assert data["title"] == "조회 테스트 타이머"
    assert "schedule" in data


@pytest.mark.e2e
def test_get_timer_not_found_e2e(e2e_client):
    """존재하지 않는 타이머 조회 E2E 테스트"""
    non_existent_id = str(uuid4())
    response = e2e_client.get(f"/v1/timers/{non_existent_id}")
    
    assert response.status_code == 404
    assert "not found" in response.json()["message"].lower()


@pytest.mark.e2e
def test_pause_timer_e2e(e2e_client):
    """HTTP를 통한 타이머 일시정지 E2E 테스트"""
    # 1. 일정 및 타이머 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "일시정지 테스트 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]
    
    timer_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "allocated_duration": 1800,
        },
    )
    timer_id = timer_response.json()["id"]
    
    # 2. 타이머 일시정지
    pause_response = e2e_client.patch(f"/v1/timers/{timer_id}/pause")
    assert pause_response.status_code == 200
    data = pause_response.json()
    assert data["status"] == "paused"
    assert data["paused_at"] is not None


@pytest.mark.e2e
def test_resume_timer_e2e(e2e_client):
    """HTTP를 통한 타이머 재개 E2E 테스트"""
    # 1. 일정 및 타이머 생성 및 일시정지
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "재개 테스트 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]
    
    timer_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "allocated_duration": 1800,
        },
    )
    timer_id = timer_response.json()["id"]
    
    # 일시정지
    e2e_client.patch(f"/v1/timers/{timer_id}/pause")
    
    # 2. 타이머 재개
    resume_response = e2e_client.patch(f"/v1/timers/{timer_id}/resume")
    assert resume_response.status_code == 200
    data = resume_response.json()
    assert data["status"] == "running"
    assert data["paused_at"] is None


@pytest.mark.e2e
def test_stop_timer_e2e(e2e_client):
    """HTTP를 통한 타이머 종료 E2E 테스트"""
    # 1. 일정 및 타이머 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "종료 테스트 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]
    
    timer_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "allocated_duration": 1800,
        },
    )
    timer_id = timer_response.json()["id"]
    
    # 2. 타이머 종료
    stop_response = e2e_client.post(f"/v1/timers/{timer_id}/stop")
    assert stop_response.status_code == 200
    data = stop_response.json()
    assert data["status"] == "completed"
    assert data["ended_at"] is not None


@pytest.mark.e2e
def test_update_timer_e2e(e2e_client):
    """HTTP를 통한 타이머 업데이트 E2E 테스트"""
    # 1. 일정 및 타이머 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "업데이트 테스트 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]
    
    timer_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "title": "원본 제목",
            "allocated_duration": 1800,
        },
    )
    timer_id = timer_response.json()["id"]
    
    # 2. 타이머 업데이트
    update_response = e2e_client.patch(
        f"/v1/timers/{timer_id}",
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
def test_delete_timer_e2e(e2e_client):
    """HTTP를 통한 타이머 삭제 E2E 테스트"""
    # 1. 일정 및 타이머 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "삭제 테스트 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]
    
    timer_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "allocated_duration": 1800,
        },
    )
    timer_id = timer_response.json()["id"]
    
    # 2. 타이머 삭제
    delete_response = e2e_client.delete(f"/v1/timers/{timer_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["ok"] is True
    
    # 3. 삭제 확인
    get_response = e2e_client.get(f"/v1/timers/{timer_id}")
    assert get_response.status_code == 404


@pytest.mark.e2e
def test_get_schedule_timers_e2e(e2e_client):
    """일정의 모든 타이머 조회 E2E 테스트"""
    # 1. 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "다중 타이머 테스트 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]
    
    # 2. 여러 타이머 생성
    timer_ids = []
    for i in range(3):
        timer_response = e2e_client.post(
            "/v1/timers",
            json={
                "schedule_id": schedule_id,
                "title": f"타이머 {i+1}",
                "allocated_duration": 1800 * (i + 1),
            },
        )
        timer_ids.append(timer_response.json()["id"])
    
    # 3. 일정의 모든 타이머 조회
    response = e2e_client.get(f"/v1/schedules/{schedule_id}/timers")
    assert response.status_code == 200
    timers = response.json()
    assert isinstance(timers, list)
    assert len(timers) >= 3
    
    # 모든 타이머가 조회되어야 함
    retrieved_ids = [t["id"] for t in timers]
    for timer_id in timer_ids:
        assert timer_id in retrieved_ids


@pytest.mark.e2e
def test_get_active_timer_e2e(e2e_client):
    """활성 타이머 조회 E2E 테스트"""
    # 1. 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "활성 타이머 테스트 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]
    
    # 2. 타이머 생성 (RUNNING 상태)
    timer_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "allocated_duration": 1800,
        },
    )
    timer_id = timer_response.json()["id"]
    
    # 3. 활성 타이머 조회
    response = e2e_client.get(f"/v1/schedules/{schedule_id}/timers/active")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == timer_id
    assert data["status"] in ["running", "paused"]


@pytest.mark.e2e
def test_get_active_timer_not_found_e2e(e2e_client):
    """활성 타이머가 없을 때 404 반환 E2E 테스트"""
    # 1. 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "활성 타이머 없음 테스트",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]
    
    # 2. 타이머 생성 후 종료
    timer_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "allocated_duration": 1800,
        },
    )
    timer_id = timer_response.json()["id"]
    e2e_client.post(f"/v1/timers/{timer_id}/stop")
    
    # 3. 활성 타이머 조회 (404 반환)
    response = e2e_client.get(f"/v1/schedules/{schedule_id}/timers/active")
    assert response.status_code == 404


@pytest.mark.e2e
def test_timer_workflow_e2e(e2e_client):
    """타이머 전체 워크플로우 E2E 테스트"""
    # 1. 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "워크플로우 테스트 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]
    
    # 2. 타이머 생성
    create_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "title": "워크플로우 타이머",
            "allocated_duration": 1800,
        },
    )
    assert create_response.status_code == 201
    timer_id = create_response.json()["id"]
    assert create_response.json()["status"] == "running"
    
    # 3. 타이머 일시정지
    pause_response = e2e_client.patch(f"/v1/timers/{timer_id}/pause")
    assert pause_response.status_code == 200
    assert pause_response.json()["status"] == "paused"
    
    # 4. 타이머 재개
    resume_response = e2e_client.patch(f"/v1/timers/{timer_id}/resume")
    assert resume_response.status_code == 200
    assert resume_response.json()["status"] == "running"
    
    # 5. 타이머 종료
    stop_response = e2e_client.post(f"/v1/timers/{timer_id}/stop")
    assert stop_response.status_code == 200
    assert stop_response.json()["status"] == "completed"
    
    # 6. 타이머 조회 확인
    get_response = e2e_client.get(f"/v1/timers/{timer_id}")
    assert get_response.status_code == 200
    assert get_response.json()["status"] == "completed"

