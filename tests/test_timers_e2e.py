"""
Timer E2E Tests

HTTP API를 통한 타이머 E2E 테스트
"""
from uuid import uuid4

import pytest


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
        params={"include_schedule": True}
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
                "title": f"타이머 {i + 1}",
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
        params={"include_schedule": True},
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


@pytest.mark.e2e
def test_timer_with_timezone_e2e(e2e_client):
    """타이머 타임존 변환 E2E 테스트"""
    # 1. 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "타이머 타임존 테스트",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]

    # 2. 타이머 생성 (타임존 포함)
    timer_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "allocated_duration": 1800,
        },
        params={"timezone": "Asia/Seoul"},
    )
    assert timer_response.status_code == 201
    data = timer_response.json()

    # 타임존 변환 확인 (+0900 형식, Python의 %z는 콜론 없음)
    if data.get("started_at"):
        assert "+0900" in data["started_at"] or data["started_at"].endswith("+0900")
    if data.get("created_at"):
        assert "+0900" in data["created_at"] or data["created_at"].endswith("+0900")

    # 3. 타이머 조회 (타임존 포함)
    timer_id = data["id"]
    get_response = e2e_client.get(
        f"/v1/timers/{timer_id}",
        params={"timezone": "+09:00"},
    )
    assert get_response.status_code == 200
    get_data = get_response.json()
    if get_data.get("started_at"):
        assert "+0900" in get_data["started_at"] or get_data["started_at"].endswith("+0900")


@pytest.mark.e2e
def test_create_timer_with_include_schedule_false_e2e(e2e_client):
    """타이머 생성 시 include_schedule=False일 때 schedule이 None인지 테스트"""
    # 1. 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "include_schedule False 테스트 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]

    # 2. 타이머 생성 (include_schedule=False)
    timer_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "allocated_duration": 1800,
        },
        params={"include_schedule": False},
    )
    assert timer_response.status_code == 201
    data = timer_response.json()
    assert "schedule" in data
    assert data["schedule"] is None


@pytest.mark.e2e
def test_create_timer_with_include_schedule_true_e2e(e2e_client):
    """타이머 생성 시 include_schedule=True일 때 schedule이 포함되는지 테스트"""
    # 1. 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "include_schedule True 테스트 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]
    schedule_title = schedule_response.json()["title"]

    # 2. 타이머 생성 (include_schedule=True, 기본값)
    timer_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "allocated_duration": 1800,
        },
        params={"include_schedule": True},
    )
    assert timer_response.status_code == 201
    data = timer_response.json()
    assert "schedule" in data
    assert data["schedule"] is not None
    assert data["schedule"]["id"] == schedule_id
    assert data["schedule"]["title"] == schedule_title


@pytest.mark.e2e
def test_get_timer_with_include_schedule_false_e2e(e2e_client):
    """타이머 조회 시 include_schedule=False일 때 schedule이 None인지 테스트"""
    # 1. 일정 및 타이머 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "조회 include_schedule False 테스트",
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

    # 2. 타이머 조회 (include_schedule=False)
    get_response = e2e_client.get(
        f"/v1/timers/{timer_id}",
        params={"include_schedule": False},
    )
    assert get_response.status_code == 200
    data = get_response.json()
    assert "schedule" in data
    assert data["schedule"] is None


@pytest.mark.e2e
def test_get_timer_with_include_schedule_true_e2e(e2e_client):
    """타이머 조회 시 include_schedule=True일 때 schedule이 포함되는지 테스트"""
    # 1. 일정 및 타이머 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "조회 include_schedule True 테스트",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]
    schedule_title = schedule_response.json()["title"]

    timer_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "allocated_duration": 1800,
        },
    )
    timer_id = timer_response.json()["id"]

    # 2. 타이머 조회 (include_schedule=True, 기본값)
    get_response = e2e_client.get(
        f"/v1/timers/{timer_id}",
        params={"include_schedule": True},
    )
    assert get_response.status_code == 200
    data = get_response.json()
    assert "schedule" in data
    assert data["schedule"] is not None
    assert data["schedule"]["id"] == schedule_id
    assert data["schedule"]["title"] == schedule_title


@pytest.mark.e2e
def test_update_timer_with_include_schedule_false_e2e(e2e_client):
    """타이머 업데이트 시 include_schedule=False일 때 schedule이 None인지 테스트"""
    # 1. 일정 및 타이머 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "업데이트 include_schedule False 테스트",
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

    # 2. 타이머 업데이트 (include_schedule=False)
    update_response = e2e_client.patch(
        f"/v1/timers/{timer_id}",
        json={"title": "업데이트된 제목"},
        params={"include_schedule": False},
    )
    assert update_response.status_code == 200
    data = update_response.json()
    assert data["title"] == "업데이트된 제목"
    assert "schedule" in data
    assert data["schedule"] is None


@pytest.mark.e2e
def test_pause_timer_with_include_schedule_false_e2e(e2e_client):
    """타이머 일시정지 시 include_schedule=False일 때 schedule이 None인지 테스트"""
    # 1. 일정 및 타이머 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "일시정지 include_schedule False 테스트",
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

    # 2. 타이머 일시정지 (include_schedule=False)
    pause_response = e2e_client.patch(
        f"/v1/timers/{timer_id}/pause",
        params={"include_schedule": False},
    )
    assert pause_response.status_code == 200
    data = pause_response.json()
    assert data["status"] == "paused"
    assert "schedule" in data
    assert data["schedule"] is None


@pytest.mark.e2e
def test_resume_timer_with_include_schedule_false_e2e(e2e_client):
    """타이머 재개 시 include_schedule=False일 때 schedule이 None인지 테스트"""
    # 1. 일정 및 타이머 생성 및 일시정지
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "재개 include_schedule False 테스트",
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
    e2e_client.patch(f"/v1/timers/{timer_id}/pause")

    # 2. 타이머 재개 (include_schedule=False)
    resume_response = e2e_client.patch(
        f"/v1/timers/{timer_id}/resume",
        params={"include_schedule": False},
    )
    assert resume_response.status_code == 200
    data = resume_response.json()
    assert data["status"] == "running"
    assert "schedule" in data
    assert data["schedule"] is None


@pytest.mark.e2e
def test_stop_timer_with_include_schedule_false_e2e(e2e_client):
    """타이머 종료 시 include_schedule=False일 때 schedule이 None인지 테스트"""
    # 1. 일정 및 타이머 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "종료 include_schedule False 테스트",
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

    # 2. 타이머 종료 (include_schedule=False)
    stop_response = e2e_client.post(
        f"/v1/timers/{timer_id}/stop",
        params={"include_schedule": False},
    )
    assert stop_response.status_code == 200
    data = stop_response.json()
    assert data["status"] == "completed"
    assert "schedule" in data
    assert data["schedule"] is None


@pytest.mark.e2e
def test_get_schedule_timers_with_include_schedule_false_e2e(e2e_client):
    """일정의 타이머 조회 시 include_schedule=False일 때 schedule이 None인지 테스트"""
    # 1. 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "타이머 리스트 include_schedule False 테스트",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]

    # 2. 타이머 생성
    timer_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "allocated_duration": 1800,
        },
    )

    # 3. 타이머 조회 (include_schedule=False)
    response = e2e_client.get(
        f"/v1/schedules/{schedule_id}/timers",
        params={"include_schedule": False},
    )
    assert response.status_code == 200
    timers = response.json()
    assert isinstance(timers, list)
    assert len(timers) > 0
    for timer in timers:
        assert "schedule" in timer
        assert timer["schedule"] is None


@pytest.mark.e2e
def test_get_schedule_timers_with_include_schedule_true_e2e(e2e_client):
    """일정의 타이머 조회 시 include_schedule=True일 때 schedule이 포함되는지 테스트"""
    # 1. 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "타이머 리스트 include_schedule True 테스트",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]
    schedule_title = schedule_response.json()["title"]

    # 2. 타이머 생성
    timer_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "allocated_duration": 1800,
        },
    )

    # 3. 타이머 조회 (include_schedule=True, 기본값)
    response = e2e_client.get(
        f"/v1/schedules/{schedule_id}/timers",
        params={"include_schedule": True},
    )
    assert response.status_code == 200
    timers = response.json()
    assert isinstance(timers, list)
    assert len(timers) > 0
    for timer in timers:
        assert "schedule" in timer
        assert timer["schedule"] is not None
        assert timer["schedule"]["id"] == schedule_id
        assert timer["schedule"]["title"] == schedule_title


@pytest.mark.e2e
def test_get_active_timer_with_include_schedule_false_e2e(e2e_client):
    """활성 타이머 조회 시 include_schedule=False일 때 schedule이 None인지 테스트"""
    # 1. 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "활성 타이머 include_schedule False 테스트",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]

    # 2. 타이머 생성
    timer_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "allocated_duration": 1800,
        },
    )

    # 3. 활성 타이머 조회 (include_schedule=False)
    response = e2e_client.get(
        f"/v1/schedules/{schedule_id}/timers/active",
        params={"include_schedule": False},
    )
    assert response.status_code == 200
    data = response.json()
    assert "schedule" in data
    assert data["schedule"] is None


@pytest.mark.e2e
def test_get_active_timer_with_include_schedule_true_e2e(e2e_client):
    """활성 타이머 조회 시 include_schedule=True일 때 schedule이 포함되는지 테스트"""
    # 1. 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "활성 타이머 include_schedule True 테스트",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]
    schedule_title = schedule_response.json()["title"]

    # 2. 타이머 생성
    timer_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "allocated_duration": 1800,
        },
    )

    # 3. 활성 타이머 조회 (include_schedule=True, 기본값)
    response = e2e_client.get(
        f"/v1/schedules/{schedule_id}/timers/active",
        params={"include_schedule": True},
    )
    assert response.status_code == 200
    data = response.json()
    assert "schedule" in data
    assert data["schedule"] is not None
    assert data["schedule"]["id"] == schedule_id
    assert data["schedule"]["title"] == schedule_title


@pytest.mark.e2e
def test_create_timer_with_tags_e2e(e2e_client):
    """타이머 생성 시 태그 함께 설정 E2E"""
    # 1. 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "태그 테스트 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]

    # 2. 그룹 및 태그 생성
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

    # 3. 타이머 생성 시 태그 함께 설정
    timer_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "title": "태그 테스트 타이머",
            "allocated_duration": 1800,
            "tag_ids": [tag_id],
        },
        params={"tag_include_mode": "timer_only"}
    )
    assert timer_response.status_code == 201
    timer_data = timer_response.json()
    timer_id = timer_data["id"]

    # 타이머의 태그 확인
    assert "tags" in timer_data
    tags = timer_data["tags"]
    assert len(tags) == 1
    assert tags[0]["id"] == tag_id
    assert tags[0]["name"] == "중요"


@pytest.mark.e2e
def test_update_timer_tags_e2e(e2e_client):
    """타이머 수정 시 태그 업데이트 E2E"""
    # 1. 일정 및 타이머 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "태그 업데이트 테스트 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]

    timer_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "title": "태그 업데이트 테스트 타이머",
            "allocated_duration": 1800,
        },
    )
    timer_id = timer_response.json()["id"]

    # 2. 그룹 및 태그 생성
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

    # 3. 타이머 수정 시 태그 업데이트
    update_response = e2e_client.patch(
        f"/v1/timers/{timer_id}",
        json={"tag_ids": [tag1_id, tag2_id]},
        params={"tag_include_mode": "timer_only"}
    )
    assert update_response.status_code == 200
    timer_data = update_response.json()

    # 타이머의 태그 확인
    assert "tags" in timer_data
    tags = timer_data["tags"]
    assert len(tags) == 2
    tag_ids = [t["id"] for t in tags]
    assert tag1_id in tag_ids
    assert tag2_id in tag_ids


@pytest.mark.e2e
def test_get_timer_with_tag_include_mode_none_e2e(e2e_client):
    """타이머 조회 시 tag_include_mode=none일 때 tags가 빈 배열인지 테스트"""
    # 1. 일정 및 타이머 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "조회 tag_include_mode none 테스트",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]

    # 2. 그룹 및 태그 생성
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

    # 3. 타이머 생성 시 태그 설정
    timer_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "allocated_duration": 1800,
            "tag_ids": [tag_id],
        },
    )
    timer_id = timer_response.json()["id"]

    # 4. 타이머 조회 (tag_include_mode=none)
    get_response = e2e_client.get(
        f"/v1/timers/{timer_id}",
        params={"tag_include_mode": "none"},
    )
    assert get_response.status_code == 200
    data = get_response.json()
    assert "tags" in data
    assert data["tags"] == []  # 빈 배열


@pytest.mark.e2e
def test_get_timer_with_tag_include_mode_timer_only_e2e(e2e_client):
    """타이머 조회 시 tag_include_mode=timer_only일 때 tags가 포함되는지 테스트"""
    # 1. 일정 및 타이머 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "조회 tag_include_mode timer_only 테스트",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]

    # 2. 그룹 및 태그 생성
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
    tag_name = tag_response.json()["name"]

    # 3. 타이머 생성 시 태그 설정
    timer_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "allocated_duration": 1800,
            "tag_ids": [tag_id],
        },
    )
    timer_id = timer_response.json()["id"]

    # 4. 타이머 조회 (tag_include_mode=timer_only)
    get_response = e2e_client.get(
        f"/v1/timers/{timer_id}",
        params={"tag_include_mode": "timer_only"},
    )
    assert get_response.status_code == 200
    data = get_response.json()
    assert "tags" in data
    assert len(data["tags"]) == 1
    assert data["tags"][0]["id"] == tag_id
    assert data["tags"][0]["name"] == tag_name


@pytest.mark.e2e
def test_update_timer_with_tag_include_mode_none_e2e(e2e_client):
    """타이머 업데이트 시 tag_include_mode=none일 때 tags가 빈 배열인지 테스트"""
    # 1. 일정 및 타이머 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "업데이트 tag_include_mode none 테스트",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]

    # 2. 그룹 및 태그 생성
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

    # 3. 타이머 생성 시 태그 설정
    timer_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "title": "원본 제목",
            "allocated_duration": 1800,
            "tag_ids": [tag_id],
        },
    )
    timer_id = timer_response.json()["id"]

    # 4. 타이머 업데이트 (tag_include_mode=none)
    update_response = e2e_client.patch(
        f"/v1/timers/{timer_id}",
        json={"title": "업데이트된 제목"},
        params={"tag_include_mode": "none"},
    )
    assert update_response.status_code == 200
    data = update_response.json()
    assert data["title"] == "업데이트된 제목"
    assert "tags" in data
    assert data["tags"] == []  # 빈 배열


@pytest.mark.e2e
def test_pause_timer_with_tag_include_mode_timer_only_e2e(e2e_client):
    """타이머 일시정지 시 tag_include_mode=timer_only일 때 tags가 포함되는지 테스트"""
    # 1. 일정 및 타이머 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "일시정지 tag_include_mode timer_only 테스트",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]

    # 2. 그룹 및 태그 생성
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

    # 3. 타이머 생성 시 태그 설정
    timer_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "allocated_duration": 1800,
            "tag_ids": [tag_id],
        },
    )
    timer_id = timer_response.json()["id"]

    # 4. 타이머 일시정지 (tag_include_mode=timer_only)
    pause_response = e2e_client.patch(
        f"/v1/timers/{timer_id}/pause",
        params={"tag_include_mode": "timer_only"},
    )
    assert pause_response.status_code == 200
    data = pause_response.json()
    assert data["status"] == "paused"
    assert "tags" in data
    assert len(data["tags"]) == 1
    assert data["tags"][0]["id"] == tag_id


@pytest.mark.e2e
def test_timer_tags_workflow_e2e(e2e_client):
    """타이머 태그 전체 워크플로우 E2E 테스트"""
    # 1. 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "태그 워크플로우 테스트 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]

    # 2. 그룹 및 태그 생성
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

    # 3. 타이머 생성 시 태그 설정
    create_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "title": "태그 워크플로우 타이머",
            "allocated_duration": 1800,
            "tag_ids": [tag1_id],
        },
        params={"tag_include_mode": "timer_only"},
    )
    assert create_response.status_code == 201
    timer_id = create_response.json()["id"]
    assert len(create_response.json()["tags"]) == 1

    # 4. 타이머 태그 업데이트
    update_response = e2e_client.patch(
        f"/v1/timers/{timer_id}",
        json={"tag_ids": [tag1_id, tag2_id]},
        params={"tag_include_mode": "timer_only"},
    )
    assert update_response.status_code == 200
    assert len(update_response.json()["tags"]) == 2

    # 5. 타이머 조회 시 태그 확인
    get_response = e2e_client.get(
        f"/v1/timers/{timer_id}",
        params={"tag_include_mode": "timer_only"},
    )
    assert get_response.status_code == 200
    tags = get_response.json()["tags"]
    assert len(tags) == 2
    tag_ids = [t["id"] for t in tags]
    assert tag1_id in tag_ids
    assert tag2_id in tag_ids

    # 6. 타이머 태그 제거
    remove_response = e2e_client.patch(
        f"/v1/timers/{timer_id}",
        json={"tag_ids": []},
        params={"tag_include_mode": "timer_only"},
    )
    assert remove_response.status_code == 200
    assert len(remove_response.json()["tags"]) == 0


@pytest.mark.e2e
def test_timer_with_inherit_from_schedule_e2e(e2e_client):
    """타이머 조회 시 tag_include_mode=inherit_from_schedule일 때 스케줄 태그 상속 테스트"""
    # 1. 일정 생성 및 태그 설정
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "스케줄 태그 상속 테스트 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]

    # 2. 그룹 및 태그 생성
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "업무", "color": "#FF5733"}
    )
    group_id = group_response.json()["id"]

    schedule_tag_response = e2e_client.post(
        "/v1/tags",
        json={"name": "스케줄태그", "color": "#0000FF", "group_id": group_id}
    )
    schedule_tag_id = schedule_tag_response.json()["id"]

    timer_tag_response = e2e_client.post(
        "/v1/tags",
        json={"name": "타이머태그", "color": "#FF0000", "group_id": group_id}
    )
    timer_tag_id = timer_tag_response.json()["id"]

    # 3. 일정에 태그 설정
    e2e_client.patch(
        f"/v1/schedules/{schedule_id}",
        json={"tag_ids": [schedule_tag_id]},
    )

    # 4. 타이머 생성 시 태그 설정
    timer_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "title": "스케줄 태그 상속 테스트 타이머",
            "allocated_duration": 1800,
            "tag_ids": [timer_tag_id],
        },
    )
    timer_id = timer_response.json()["id"]

    # 5. 타이머 조회 (tag_include_mode=inherit_from_schedule)
    get_response = e2e_client.get(
        f"/v1/timers/{timer_id}",
        params={"tag_include_mode": "inherit_from_schedule"},
    )
    assert get_response.status_code == 200
    data = get_response.json()
    assert "tags" in data
    tags = data["tags"]
    # 타이머 태그 + 스케줄 태그 모두 포함되어야 함
    assert len(tags) == 2
    tag_ids = [t["id"] for t in tags]
    assert schedule_tag_id in tag_ids
    assert timer_tag_id in tag_ids

    # 6. 타이머 태그만 조회 (tag_include_mode=timer_only)
    get_timer_only_response = e2e_client.get(
        f"/v1/timers/{timer_id}",
        params={"tag_include_mode": "timer_only"},
    )
    assert get_timer_only_response.status_code == 200
    timer_only_tags = get_timer_only_response.json()["tags"]
    assert len(timer_only_tags) == 1
    assert timer_only_tags[0]["id"] == timer_tag_id


# ============================================================
# 타이머 목록 조회 E2E 테스트
# ============================================================

@pytest.mark.e2e
def test_list_timers_e2e(e2e_client):
    """타이머 목록 조회 E2E 테스트"""
    # 1. 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "목록 조회 테스트 일정",
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
                "title": f"타이머 {i + 1}",
                "allocated_duration": 1800 * (i + 1),
            },
        )
        timer_ids.append(timer_response.json()["id"])

    # 3. 타이머 목록 조회
    response = e2e_client.get("/v1/timers")
    assert response.status_code == 200
    timers = response.json()
    assert isinstance(timers, list)
    assert len(timers) >= 3

    # 모든 타이머가 조회되어야 함
    retrieved_ids = [t["id"] for t in timers]
    for timer_id in timer_ids:
        assert timer_id in retrieved_ids


@pytest.mark.e2e
def test_list_timers_with_status_filter_e2e(e2e_client):
    """상태 필터로 타이머 목록 조회 E2E 테스트"""
    # 1. 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "상태 필터 테스트 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]

    # 2. 타이머 생성 및 상태 변경
    # RUNNING 타이머
    running_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "title": "Running 타이머",
            "allocated_duration": 1800,
        },
    )
    running_id = running_response.json()["id"]

    # PAUSED 타이머
    paused_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "title": "Paused 타이머",
            "allocated_duration": 1800,
        },
    )
    paused_id = paused_response.json()["id"]
    e2e_client.patch(f"/v1/timers/{paused_id}/pause")

    # COMPLETED 타이머
    completed_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "title": "Completed 타이머",
            "allocated_duration": 1800,
        },
    )
    completed_id = completed_response.json()["id"]
    e2e_client.post(f"/v1/timers/{completed_id}/stop")

    # 3. RUNNING 상태만 조회
    running_response = e2e_client.get("/v1/timers", params={"status": "running"})
    assert running_response.status_code == 200
    running_timers = running_response.json()
    running_timer_ids = [t["id"] for t in running_timers]
    assert running_id in running_timer_ids
    assert paused_id not in running_timer_ids
    assert completed_id not in running_timer_ids

    # 4. PAUSED 상태만 조회
    paused_response = e2e_client.get("/v1/timers", params={"status": "paused"})
    assert paused_response.status_code == 200
    paused_timers = paused_response.json()
    paused_timer_ids = [t["id"] for t in paused_timers]
    assert paused_id in paused_timer_ids

    # 5. COMPLETED 상태만 조회
    completed_response = e2e_client.get("/v1/timers", params={"status": "completed"})
    assert completed_response.status_code == 200
    completed_timers = completed_response.json()
    completed_timer_ids = [t["id"] for t in completed_timers]
    assert completed_id in completed_timer_ids


@pytest.mark.e2e
def test_list_timers_with_type_filter_independent_e2e(e2e_client):
    """독립 타이머 타입 필터 E2E 테스트"""
    # 1. 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "타입 필터 테스트 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]

    # 2. 독립 타이머 생성
    independent_response = e2e_client.post(
        "/v1/timers",
        json={
            "title": "독립 타이머",
            "allocated_duration": 600,
        },
    )
    independent_id = independent_response.json()["id"]

    # 3. 연결된 타이머 생성
    linked_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "title": "연결된 타이머",
            "allocated_duration": 1800,
        },
    )
    linked_id = linked_response.json()["id"]

    # 4. 독립 타이머만 조회
    response = e2e_client.get("/v1/timers", params={"type": "independent"})
    assert response.status_code == 200
    timers = response.json()
    timer_ids = [t["id"] for t in timers]
    assert independent_id in timer_ids
    assert linked_id not in timer_ids


@pytest.mark.e2e
def test_list_timers_with_type_filter_schedule_e2e(e2e_client):
    """Schedule 연결 타이머 타입 필터 E2E 테스트"""
    # 1. 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "Schedule 타입 필터 테스트",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]

    # 2. Schedule 연결 타이머 생성
    schedule_timer_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "title": "Schedule 연결 타이머",
            "allocated_duration": 1800,
        },
    )
    schedule_timer_id = schedule_timer_response.json()["id"]

    # 3. 독립 타이머 생성
    independent_response = e2e_client.post(
        "/v1/timers",
        json={
            "title": "독립 타이머",
            "allocated_duration": 600,
        },
    )
    independent_id = independent_response.json()["id"]

    # 4. Schedule 연결 타이머만 조회
    response = e2e_client.get("/v1/timers", params={"type": "schedule"})
    assert response.status_code == 200
    timers = response.json()
    timer_ids = [t["id"] for t in timers]
    assert schedule_timer_id in timer_ids
    assert independent_id not in timer_ids


@pytest.mark.e2e
def test_get_user_active_timer_e2e(e2e_client):
    """사용자의 활성 타이머 조회 E2E 테스트"""
    # 1. 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "사용자 활성 타이머 테스트",
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
            "title": "활성 타이머",
            "allocated_duration": 1800,
        },
    )
    timer_id = timer_response.json()["id"]

    # 3. 사용자 활성 타이머 조회
    response = e2e_client.get("/v1/timers/active")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == timer_id
    assert data["status"] == "running"


@pytest.mark.e2e
def test_get_user_active_timer_paused_e2e(e2e_client):
    """일시정지된 타이머도 활성 타이머로 조회 E2E 테스트"""
    # 1. 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "일시정지 활성 타이머 테스트",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]

    # 2. 타이머 생성 후 일시정지
    timer_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "title": "일시정지 타이머",
            "allocated_duration": 1800,
        },
    )
    timer_id = timer_response.json()["id"]
    e2e_client.patch(f"/v1/timers/{timer_id}/pause")

    # 3. 사용자 활성 타이머 조회
    response = e2e_client.get("/v1/timers/active")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == timer_id
    assert data["status"] == "paused"


@pytest.mark.e2e
def test_get_user_active_timer_not_found_e2e(e2e_client):
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

    # 3. 사용자 활성 타이머 조회 (404 반환)
    response = e2e_client.get("/v1/timers/active")
    assert response.status_code == 404


@pytest.mark.e2e
def test_list_timers_with_include_schedule_e2e(e2e_client):
    """타이머 목록 조회 시 include_schedule 옵션 E2E 테스트"""
    # 1. 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "include_schedule 옵션 테스트",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]
    schedule_title = schedule_response.json()["title"]

    # 2. 타이머 생성
    e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "title": "include_schedule 테스트 타이머",
            "allocated_duration": 1800,
        },
    )

    # 3. include_schedule=True로 조회
    response = e2e_client.get(
        "/v1/timers",
        params={"type": "schedule", "include_schedule": True}
    )
    assert response.status_code == 200
    timers = response.json()
    assert len(timers) > 0
    # schedule 정보 포함 확인
    timer = next((t for t in timers if t.get("schedule_id") == schedule_id), None)
    assert timer is not None
    assert timer["schedule"] is not None
    assert timer["schedule"]["id"] == schedule_id
    assert timer["schedule"]["title"] == schedule_title


@pytest.mark.e2e
def test_get_user_active_timer_with_include_schedule_e2e(e2e_client):
    """사용자 활성 타이머 조회 시 include_schedule 옵션 E2E 테스트"""
    # 1. 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "활성 타이머 include_schedule 테스트",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]
    schedule_title = schedule_response.json()["title"]

    # 2. 타이머 생성
    e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "title": "활성 타이머",
            "allocated_duration": 1800,
        },
    )

    # 3. include_schedule=True로 활성 타이머 조회
    response = e2e_client.get(
        "/v1/timers/active",
        params={"include_schedule": True}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["schedule"] is not None
    assert data["schedule"]["id"] == schedule_id
    assert data["schedule"]["title"] == schedule_title


# ============================================================
# 타이머 목록 필터링 E2E 테스트 (대소문자 및 복수 상태 필터)
# ============================================================

@pytest.mark.e2e
def test_list_timers_with_uppercase_status_filter_e2e(e2e_client):
    """대문자 status 필터로 타이머 목록 조회 E2E 테스트 (프론트엔드 호환성)"""
    # 1. 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "대문자 status 필터 테스트",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]

    # 2. RUNNING 타이머 생성
    running_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "title": "Running 타이머",
            "allocated_duration": 1800,
        },
    )
    running_id = running_response.json()["id"]

    # 3. 대문자 "RUNNING"으로 조회 (프론트엔드 방식)
    response = e2e_client.get("/v1/timers", params={"status": "RUNNING"})
    assert response.status_code == 200
    timers = response.json()
    timer_ids = [t["id"] for t in timers]
    assert running_id in timer_ids


@pytest.mark.e2e
def test_list_timers_with_multiple_status_filter_e2e(e2e_client):
    """복수 status 필터로 타이머 목록 조회 E2E 테스트"""
    # 1. 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "복수 status 필터 테스트",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]

    # 2. RUNNING 타이머 생성
    running_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "title": "Running 타이머",
            "allocated_duration": 1800,
        },
    )
    running_id = running_response.json()["id"]

    # 3. PAUSED 타이머 생성
    paused_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "title": "Paused 타이머",
            "allocated_duration": 1800,
        },
    )
    paused_id = paused_response.json()["id"]
    e2e_client.patch(f"/v1/timers/{paused_id}/pause")

    # 4. COMPLETED 타이머 생성
    completed_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "title": "Completed 타이머",
            "allocated_duration": 1800,
        },
    )
    completed_id = completed_response.json()["id"]
    e2e_client.post(f"/v1/timers/{completed_id}/stop")

    # 5. 복수 상태로 조회 (RUNNING, PAUSED)
    response = e2e_client.get("/v1/timers", params=[("status", "running"), ("status", "paused")])
    assert response.status_code == 200
    timers = response.json()
    timer_ids = [t["id"] for t in timers]

    # RUNNING, PAUSED 타이머만 포함
    assert running_id in timer_ids
    assert paused_id in timer_ids
    # COMPLETED 타이머는 제외
    assert completed_id not in timer_ids


@pytest.mark.e2e
def test_list_timers_with_uppercase_multiple_status_filter_e2e(e2e_client):
    """대문자 복수 status 필터로 타이머 목록 조회 E2E 테스트 (프론트엔드 호환성)"""
    # 1. 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "대문자 복수 status 필터 테스트",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]

    # 2. RUNNING 타이머 생성
    running_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "title": "Running 타이머",
            "allocated_duration": 1800,
        },
    )
    running_id = running_response.json()["id"]

    # 3. PAUSED 타이머 생성
    paused_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "title": "Paused 타이머",
            "allocated_duration": 1800,
        },
    )
    paused_id = paused_response.json()["id"]
    e2e_client.patch(f"/v1/timers/{paused_id}/pause")

    # 4. 대문자 복수 상태로 조회 (RUNNING, PAUSED) - 프론트엔드 방식
    response = e2e_client.get("/v1/timers", params=[("status", "RUNNING"), ("status", "PAUSED")])
    assert response.status_code == 200
    timers = response.json()
    timer_ids = [t["id"] for t in timers]

    # RUNNING, PAUSED 타이머 모두 포함
    assert running_id in timer_ids
    assert paused_id in timer_ids


@pytest.mark.e2e
def test_list_timers_active_consistency_e2e(e2e_client):
    """
    /v1/timers?status=RUNNING&status=PAUSED와 /v1/timers/active 일관성 테스트
    
    프론트엔드 이슈: 두 API의 결과가 일치해야 함
    """
    # 1. 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "API 일관성 테스트",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]

    # 2. RUNNING 타이머 생성
    timer_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "title": "활성 타이머",
            "allocated_duration": 1800,
        },
    )
    timer_id = timer_response.json()["id"]

    # 3. /v1/timers/active 조회
    active_response = e2e_client.get(
        "/v1/timers/active",
        params={"include_schedule": True, "include_todo": True}
    )
    assert active_response.status_code == 200
    active_timer = active_response.json()
    assert active_timer["id"] == timer_id

    # 4. /v1/timers?status=RUNNING&status=PAUSED 조회 (대문자)
    list_response = e2e_client.get(
        "/v1/timers",
        params=[
            ("status", "RUNNING"),
            ("status", "PAUSED"),
            ("include_schedule", True),
            ("include_todo", True),
        ]
    )
    assert list_response.status_code == 200
    timers = list_response.json()

    # 목록에서 해당 타이머 찾기
    timer_ids = [t["id"] for t in timers]
    assert timer_id in timer_ids, "활성 타이머가 목록에 포함되어야 함"


@pytest.mark.e2e
def test_list_timers_mixed_case_status_filter_e2e(e2e_client):
    """대소문자 혼합 status 필터 테스트"""
    # 1. 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "혼합 대소문자 status 필터 테스트",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]

    # 2. RUNNING 타이머 생성
    timer_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "title": "Running 타이머",
            "allocated_duration": 1800,
        },
    )
    timer_id = timer_response.json()["id"]

    # 3. 혼합 대소문자로 조회 (Running, Paused)
    response = e2e_client.get("/v1/timers", params=[("status", "Running"), ("status", "Paused")])
    assert response.status_code == 200
    timers = response.json()
    timer_ids = [t["id"] for t in timers]
    assert timer_id in timer_ids


# ============================================================
# 타이머 목록 날짜 필터링 E2E 테스트
# ============================================================

@pytest.mark.e2e
def test_list_timers_with_date_range_filter_e2e(e2e_client):
    """날짜 범위 필터로 타이머 목록 조회 E2E 테스트"""
    # 1. 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "날짜 필터 테스트",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]

    # 2. 타이머 생성
    timer_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "title": "날짜 필터 테스트 타이머",
            "allocated_duration": 1800,
        },
    )
    timer_id = timer_response.json()["id"]

    # 3. 오늘 날짜 범위로 조회 (타이머가 포함되어야 함)
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    start_date = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_date = (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

    response = e2e_client.get(
        "/v1/timers",
        params={"start_date": start_date, "end_date": end_date}
    )
    assert response.status_code == 200
    timers = response.json()
    timer_ids = [t["id"] for t in timers]
    assert timer_id in timer_ids


@pytest.mark.e2e
def test_list_timers_with_future_date_range_filter_e2e(e2e_client):
    """미래 날짜 범위로 필터링 시 결과가 없어야 함"""
    # 1. 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "미래 날짜 필터 테스트",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]

    # 2. 타이머 생성
    e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "title": "미래 날짜 필터 테스트 타이머",
            "allocated_duration": 1800,
        },
    )

    # 3. 미래 날짜 범위로 조회
    from datetime import datetime, timedelta, timezone
    future_start = (datetime.now(timezone.utc) + timedelta(days=100)).strftime("%Y-%m-%dT%H:%M:%SZ")
    future_end = (datetime.now(timezone.utc) + timedelta(days=101)).strftime("%Y-%m-%dT%H:%M:%SZ")

    response = e2e_client.get(
        "/v1/timers",
        params={"start_date": future_start, "end_date": future_end}
    )
    assert response.status_code == 200
    timers = response.json()
    # 미래 날짜 범위이므로 현재 생성된 타이머는 포함되지 않아야 함
    assert len(timers) == 0


# ============================================================
# 타이머 목록 Todo 타입 필터링 E2E 테스트
# ============================================================

@pytest.mark.e2e
def test_list_timers_with_type_filter_todo_e2e(e2e_client):
    """Todo 연결 타이머 타입 필터 E2E 테스트"""
    # 1. 태그 그룹 생성 (Todo 생성에 필요)
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "Todo 필터 테스트 그룹", "color": "#FF5733"}
    )
    group_id = group_response.json()["id"]

    # 2. Todo 생성
    todo_response = e2e_client.post(
        "/v1/todos",
        json={
            "title": "Todo 타입 필터 테스트",
            "duration": 3600,
            "tag_group_id": group_id,
        },
    )
    assert todo_response.status_code == 201
    todo_id = todo_response.json()["id"]

    # 3. Todo 연결 타이머 생성
    todo_timer_response = e2e_client.post(
        "/v1/timers",
        json={
            "todo_id": todo_id,
            "title": "Todo 연결 타이머",
            "allocated_duration": 1800,
        },
    )
    todo_timer_id = todo_timer_response.json()["id"]

    # 4. 독립 타이머 생성
    independent_response = e2e_client.post(
        "/v1/timers",
        json={
            "title": "독립 타이머",
            "allocated_duration": 600,
        },
    )
    independent_id = independent_response.json()["id"]

    # 5. Todo 연결 타이머만 조회
    response = e2e_client.get("/v1/timers", params={"type": "todo"})
    assert response.status_code == 200
    timers = response.json()
    timer_ids = [t["id"] for t in timers]
    assert todo_timer_id in timer_ids
    assert independent_id not in timer_ids


@pytest.mark.e2e
def test_list_timers_with_include_todo_e2e(e2e_client):
    """타이머 목록 조회 시 include_todo 옵션 E2E 테스트"""
    # 1. 태그 그룹 생성 (Todo 생성에 필요)
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "include_todo 테스트 그룹", "color": "#FF5733"}
    )
    group_id = group_response.json()["id"]

    # 2. Todo 생성
    todo_response = e2e_client.post(
        "/v1/todos",
        json={
            "title": "include_todo 테스트",
            "duration": 3600,
            "tag_group_id": group_id,
        },
    )
    assert todo_response.status_code == 201
    todo_id = todo_response.json()["id"]
    todo_title = todo_response.json()["title"]

    # 3. Todo 연결 타이머 생성
    e2e_client.post(
        "/v1/timers",
        json={
            "todo_id": todo_id,
            "title": "include_todo 테스트 타이머",
            "allocated_duration": 1800,
        },
    )

    # 4. include_todo=True로 조회
    response = e2e_client.get(
        "/v1/timers",
        params={"type": "todo", "include_todo": True}
    )
    assert response.status_code == 200
    timers = response.json()
    assert len(timers) > 0

    # todo 정보 포함 확인
    timer = next((t for t in timers if t.get("todo_id") == todo_id), None)
    assert timer is not None
    assert timer["todo"] is not None
    assert timer["todo"]["id"] == todo_id
    assert timer["todo"]["title"] == todo_title


# ============================================================
# 복합 필터링 E2E 테스트
# ============================================================

@pytest.mark.e2e
def test_list_timers_with_combined_filters_e2e(e2e_client):
    """복합 필터 (status + type) E2E 테스트"""
    # 1. 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "복합 필터 테스트",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]

    # 2. Schedule 연결 RUNNING 타이머
    schedule_running_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "title": "Schedule Running 타이머",
            "allocated_duration": 1800,
        },
    )
    schedule_running_id = schedule_running_response.json()["id"]

    # 3. 독립 RUNNING 타이머
    independent_response = e2e_client.post(
        "/v1/timers",
        json={
            "title": "독립 Running 타이머",
            "allocated_duration": 600,
        },
    )
    independent_id = independent_response.json()["id"]

    # 4. Schedule 연결 COMPLETED 타이머
    schedule_completed_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "title": "Schedule Completed 타이머",
            "allocated_duration": 1800,
        },
    )
    schedule_completed_id = schedule_completed_response.json()["id"]
    e2e_client.post(f"/v1/timers/{schedule_completed_id}/stop")

    # 5. status=RUNNING + type=schedule 조합 필터
    response = e2e_client.get(
        "/v1/timers",
        params={"status": "RUNNING", "type": "schedule"}
    )
    assert response.status_code == 200
    timers = response.json()
    timer_ids = [t["id"] for t in timers]

    # Schedule 연결 RUNNING 타이머만 포함
    assert schedule_running_id in timer_ids
    # 독립 타이머 제외
    assert independent_id not in timer_ids
    # COMPLETED 타이머 제외
    assert schedule_completed_id not in timer_ids


@pytest.mark.e2e
def test_list_timers_with_all_options_e2e(e2e_client):
    """모든 옵션 (status + type + include_schedule + include_todo + timezone) E2E 테스트"""
    # 1. 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "모든 옵션 테스트",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]

    # 2. 타이머 생성
    timer_response = e2e_client.post(
        "/v1/timers",
        json={
            "schedule_id": schedule_id,
            "title": "모든 옵션 테스트 타이머",
            "allocated_duration": 1800,
        },
    )
    timer_id = timer_response.json()["id"]

    # 3. 모든 옵션으로 조회
    response = e2e_client.get(
        "/v1/timers",
        params={
            "status": "RUNNING",
            "type": "schedule",
            "include_schedule": True,
            "include_todo": True,
            "timezone": "Asia/Seoul",
        }
    )
    assert response.status_code == 200
    timers = response.json()
    timer_ids = [t["id"] for t in timers]
    assert timer_id in timer_ids

    # 옵션 적용 확인
    timer = next(t for t in timers if t["id"] == timer_id)
    assert timer["schedule"] is not None
    # 타임존 변환 확인 (+0900)
    if timer.get("started_at"):
        assert "+0900" in timer["started_at"] or timer["started_at"].endswith("+0900")
