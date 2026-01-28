"""
Timer E2E Tests

HTTP API를 통한 타이머 E2E 테스트

[WebSocket 전환 - 2026-01-28]
타이머 생성/일시정지/재개/종료는 WebSocket으로 이동되었습니다.
- WebSocket 테스트: tests/test_websocket_timers.py
- REST API는 조회/업데이트/삭제만 테스트
"""
import json
from uuid import uuid4

import pytest


# ============================================================
# WebSocket 타이머 헬퍼 함수
# ============================================================

def create_timer_via_websocket(
    client,
    schedule_id: str = None,
    todo_id: str = None,
    title: str = "테스트 타이머",
    allocated_duration: int = 1800,
    tag_ids: list = None,
):
    """
    WebSocket을 통해 타이머 생성
    
    E2E 테스트에서 타이머를 생성할 때 사용합니다.
    REST API 엔드포인트가 WebSocket으로 이동되었기 때문입니다.
    """
    payload = {
        "type": "timer.create",
        "payload": {
            "title": title,
            "allocated_duration": allocated_duration,
        }
    }
    
    if schedule_id:
        payload["payload"]["schedule_id"] = schedule_id
    if todo_id:
        payload["payload"]["todo_id"] = todo_id
    if tag_ids:
        payload["payload"]["tag_ids"] = tag_ids
    
    with client.websocket_connect("/v1/ws/timers") as ws:
        # 연결 메시지 수신 (connected)
        connected_msg = ws.receive_json()
        assert connected_msg.get("type") == "connected", f"Expected 'connected', got: {connected_msg}"
        
        # 타이머 생성 요청
        ws.send_text(json.dumps(payload))
        response = ws.receive_json()
        
        # 에러 응답 처리
        if response.get("type") == "error":
            raise Exception(f"Timer creation failed: {response.get('payload', {}).get('message', response)}")
        
        # timer.created 응답에서 timer 데이터 반환
        return response.get("payload", {}).get("timer", response)


def pause_timer_via_websocket(client, timer_id: str):
    """WebSocket을 통해 타이머 일시정지"""
    payload = {
        "type": "timer.pause",
        "payload": {"timer_id": timer_id}
    }
    
    with client.websocket_connect("/v1/ws/timers") as ws:
        # 연결 메시지 수신 (connected)
        ws.receive_json()
        
        ws.send_text(json.dumps(payload))
        response = ws.receive_json()
        return response.get("payload", {}).get("timer", response)


def resume_timer_via_websocket(client, timer_id: str):
    """WebSocket을 통해 타이머 재개"""
    payload = {
        "type": "timer.resume",
        "payload": {"timer_id": timer_id}
    }
    
    with client.websocket_connect("/v1/ws/timers") as ws:
        # 연결 메시지 수신 (connected)
        ws.receive_json()
        
        ws.send_text(json.dumps(payload))
        response = ws.receive_json()
        return response.get("payload", {}).get("timer", response)


def stop_timer_via_websocket(client, timer_id: str):
    """WebSocket을 통해 타이머 종료"""
    payload = {
        "type": "timer.stop",
        "payload": {"timer_id": timer_id}
    }
    
    with client.websocket_connect("/v1/ws/timers") as ws:
        # 연결 메시지 수신 (connected)
        ws.receive_json()
        
        ws.send_text(json.dumps(payload))
        response = ws.receive_json()
        return response.get("payload", {}).get("timer", response)


# ============================================================
# 타이머 조회 E2E 테스트 (REST API)
# ============================================================

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

    # 2. 타이머 생성 (WebSocket)
    timer_data = create_timer_via_websocket(
        e2e_client,
        schedule_id=schedule_id,
        title="조회 테스트 타이머",
        allocated_duration=1800,
    )
    timer_id = timer_data["id"]

    # 3. 타이머 조회 (REST API)
    get_response = e2e_client.get(f"/v1/timers/{timer_id}")
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["id"] == timer_id
    assert data["title"] == "조회 테스트 타이머"


@pytest.mark.e2e
def test_get_timer_not_found_e2e(e2e_client):
    """존재하지 않는 타이머 조회 E2E 테스트"""
    non_existent_id = str(uuid4())
    response = e2e_client.get(f"/v1/timers/{non_existent_id}")

    assert response.status_code == 404
    assert "not found" in response.json()["message"].lower()


@pytest.mark.e2e
def test_get_timer_with_include_schedule_e2e(e2e_client):
    """타이머 조회 시 include_schedule 옵션 테스트"""
    # 1. 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "include_schedule 테스트",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]
    schedule_title = schedule_response.json()["title"]

    # 2. 타이머 생성 (WebSocket)
    timer_data = create_timer_via_websocket(
        e2e_client,
        schedule_id=schedule_id,
        allocated_duration=1800,
    )
    timer_id = timer_data["id"]

    # 3. include_schedule=True로 조회
    get_response = e2e_client.get(
        f"/v1/timers/{timer_id}",
        params={"include_schedule": True},
    )
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["schedule"] is not None
    assert data["schedule"]["id"] == schedule_id
    assert data["schedule"]["title"] == schedule_title

    # 4. include_schedule=False로 조회
    get_response = e2e_client.get(
        f"/v1/timers/{timer_id}",
        params={"include_schedule": False},
    )
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["schedule"] is None


# ============================================================
# 타이머 업데이트 E2E 테스트 (REST API)
# ============================================================

@pytest.mark.e2e
def test_update_timer_e2e(e2e_client):
    """HTTP를 통한 타이머 업데이트 E2E 테스트"""
    # 1. 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "업데이트 테스트 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]

    # 2. 타이머 생성 (WebSocket)
    timer_data = create_timer_via_websocket(
        e2e_client,
        schedule_id=schedule_id,
        title="원본 제목",
        allocated_duration=1800,
    )
    timer_id = timer_data["id"]

    # 3. 타이머 업데이트 (REST API)
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

    timer_data = create_timer_via_websocket(
        e2e_client,
        schedule_id=schedule_id,
        title="태그 업데이트 테스트 타이머",
        allocated_duration=1800,
    )
    timer_id = timer_data["id"]

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


# ============================================================
# 타이머 삭제 E2E 테스트 (REST API)
# ============================================================

@pytest.mark.e2e
def test_delete_timer_e2e(e2e_client):
    """HTTP를 통한 타이머 삭제 E2E 테스트"""
    # 1. 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "삭제 테스트 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]

    # 2. 타이머 생성 (WebSocket)
    timer_data = create_timer_via_websocket(
        e2e_client,
        schedule_id=schedule_id,
        allocated_duration=1800,
    )
    timer_id = timer_data["id"]

    # 3. 타이머 삭제 (REST API)
    delete_response = e2e_client.delete(f"/v1/timers/{timer_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["ok"] is True

    # 4. 삭제 확인
    get_response = e2e_client.get(f"/v1/timers/{timer_id}")
    assert get_response.status_code == 404


# ============================================================
# 타이머 목록 조회 E2E 테스트 (REST API)
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

    # 2. 여러 타이머 생성 (WebSocket)
    timer_ids = []
    for i in range(3):
        timer_data = create_timer_via_websocket(
            e2e_client,
            schedule_id=schedule_id,
            title=f"타이머 {i + 1}",
            allocated_duration=1800 * (i + 1),
        )
        timer_ids.append(timer_data["id"])

    # 3. 타이머 목록 조회 (REST API)
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

    # 2. RUNNING 타이머 생성
    running_data = create_timer_via_websocket(
        e2e_client,
        schedule_id=schedule_id,
        title="Running 타이머",
        allocated_duration=1800,
    )
    running_id = running_data["id"]

    # 3. PAUSED 타이머 생성
    paused_data = create_timer_via_websocket(
        e2e_client,
        schedule_id=schedule_id,
        title="Paused 타이머",
        allocated_duration=1800,
    )
    paused_id = paused_data["id"]
    pause_timer_via_websocket(e2e_client, paused_id)

    # 4. COMPLETED 타이머 생성
    completed_data = create_timer_via_websocket(
        e2e_client,
        schedule_id=schedule_id,
        title="Completed 타이머",
        allocated_duration=1800,
    )
    completed_id = completed_data["id"]
    stop_timer_via_websocket(e2e_client, completed_id)

    # 5. RUNNING 상태만 조회
    running_response = e2e_client.get("/v1/timers", params={"status": "running"})
    assert running_response.status_code == 200
    running_timers = running_response.json()
    running_timer_ids = [t["id"] for t in running_timers]
    assert running_id in running_timer_ids
    assert paused_id not in running_timer_ids
    assert completed_id not in running_timer_ids

    # 6. PAUSED 상태만 조회
    paused_response = e2e_client.get("/v1/timers", params={"status": "paused"})
    assert paused_response.status_code == 200
    paused_timers = paused_response.json()
    paused_timer_ids = [t["id"] for t in paused_timers]
    assert paused_id in paused_timer_ids

    # 7. COMPLETED 상태만 조회
    completed_response = e2e_client.get("/v1/timers", params={"status": "completed"})
    assert completed_response.status_code == 200
    completed_timers = completed_response.json()
    completed_timer_ids = [t["id"] for t in completed_timers]
    assert completed_id in completed_timer_ids


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
    timer_data = create_timer_via_websocket(
        e2e_client,
        schedule_id=schedule_id,
        title="Running 타이머",
        allocated_duration=1800,
    )
    timer_id = timer_data["id"]

    # 3. 대문자 "RUNNING"으로 조회 (프론트엔드 방식)
    response = e2e_client.get("/v1/timers", params={"status": "RUNNING"})
    assert response.status_code == 200
    timers = response.json()
    timer_ids = [t["id"] for t in timers]
    assert timer_id in timer_ids


@pytest.mark.e2e
def test_list_timers_with_mixed_case_status_filter_e2e(e2e_client):
    """대소문자 혼합 status 필터로 타이머 목록 조회 E2E 테스트 (프론트엔드 호환성)"""
    # 1. 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "대소문자 혼합 status 필터 테스트",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]

    # 2. RUNNING 타이머 생성
    running_data = create_timer_via_websocket(
        e2e_client,
        schedule_id=schedule_id,
        title="Running 타이머",
        allocated_duration=1800,
    )
    running_id = running_data["id"]

    # 3. PAUSED 타이머 생성
    paused_data = create_timer_via_websocket(
        e2e_client,
        schedule_id=schedule_id,
        title="Paused 타이머",
        allocated_duration=1800,
    )
    paused_id = paused_data["id"]
    pause_timer_via_websocket(e2e_client, paused_id)

    # 4. COMPLETED 타이머 생성
    completed_data = create_timer_via_websocket(
        e2e_client,
        schedule_id=schedule_id,
        title="Completed 타이머",
        allocated_duration=1800,
    )
    completed_id = completed_data["id"]
    stop_timer_via_websocket(e2e_client, completed_id)

    # 5. 대소문자 혼합 "Running"으로 조회
    response = e2e_client.get("/v1/timers", params={"status": "Running"})
    assert response.status_code == 200
    timers = response.json()
    timer_ids = [t["id"] for t in timers]
    assert running_id in timer_ids
    assert paused_id not in timer_ids
    assert completed_id not in timer_ids

    # 6. 대소문자 혼합 "Paused"로 조회
    response = e2e_client.get("/v1/timers", params={"status": "Paused"})
    assert response.status_code == 200
    timers = response.json()
    timer_ids = [t["id"] for t in timers]
    assert paused_id in timer_ids
    assert running_id not in timer_ids
    assert completed_id not in timer_ids

    # 7. 대소문자 혼합 "Completed"로 조회
    response = e2e_client.get("/v1/timers", params={"status": "Completed"})
    assert response.status_code == 200
    timers = response.json()
    timer_ids = [t["id"] for t in timers]
    assert completed_id in timer_ids
    assert running_id not in timer_ids
    assert paused_id not in timer_ids


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
    running_data = create_timer_via_websocket(
        e2e_client,
        schedule_id=schedule_id,
        title="Running 타이머",
        allocated_duration=1800,
    )
    running_id = running_data["id"]

    # 3. PAUSED 타이머 생성
    paused_data = create_timer_via_websocket(
        e2e_client,
        schedule_id=schedule_id,
        title="Paused 타이머",
        allocated_duration=1800,
    )
    paused_id = paused_data["id"]
    pause_timer_via_websocket(e2e_client, paused_id)

    # 4. COMPLETED 타이머 생성
    completed_data = create_timer_via_websocket(
        e2e_client,
        schedule_id=schedule_id,
        title="Completed 타이머",
        allocated_duration=1800,
    )
    completed_id = completed_data["id"]
    stop_timer_via_websocket(e2e_client, completed_id)

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
    independent_data = create_timer_via_websocket(
        e2e_client,
        title="독립 타이머",
        allocated_duration=600,
    )
    independent_id = independent_data["id"]

    # 3. Schedule 연결 타이머 생성
    linked_data = create_timer_via_websocket(
        e2e_client,
        schedule_id=schedule_id,
        title="연결된 타이머",
        allocated_duration=1800,
    )
    linked_id = linked_data["id"]

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
    schedule_timer_data = create_timer_via_websocket(
        e2e_client,
        schedule_id=schedule_id,
        title="Schedule 연결 타이머",
        allocated_duration=1800,
    )
    schedule_timer_id = schedule_timer_data["id"]

    # 3. 독립 타이머 생성
    independent_data = create_timer_via_websocket(
        e2e_client,
        title="독립 타이머",
        allocated_duration=600,
    )
    independent_id = independent_data["id"]

    # 4. Schedule 연결 타이머만 조회
    response = e2e_client.get("/v1/timers", params={"type": "schedule"})
    assert response.status_code == 200
    timers = response.json()
    timer_ids = [t["id"] for t in timers]
    assert schedule_timer_id in timer_ids
    assert independent_id not in timer_ids


@pytest.mark.e2e
def test_list_timers_with_include_schedule_e2e(e2e_client):
    """타이머 목록 조회 시 include_schedule 옵션 E2E 테스트"""
    # 1. 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "include_schedule 목록 테스트",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = schedule_response.json()["id"]
    schedule_title = schedule_response.json()["title"]

    # 2. Schedule에 연결된 타이머 생성 (WebSocket)
    timer_data = create_timer_via_websocket(
        e2e_client,
        schedule_id=schedule_id,
        title="include_schedule 테스트 타이머",
        allocated_duration=1800,
    )
    timer_id = timer_data["id"]

    # 3. include_schedule=True로 목록 조회
    response = e2e_client.get(
        "/v1/timers",
        params={"include_schedule": True}
    )
    assert response.status_code == 200
    timers = response.json()

    # 해당 타이머 찾기
    timer = next((t for t in timers if t["id"] == timer_id), None)
    assert timer is not None
    assert timer["schedule"] is not None
    assert timer["schedule"]["id"] == schedule_id
    assert timer["schedule"]["title"] == schedule_title

    # 4. include_schedule=False로 목록 조회
    response = e2e_client.get(
        "/v1/timers",
        params={"include_schedule": False}
    )
    assert response.status_code == 200
    timers = response.json()

    # 해당 타이머 찾기
    timer = next((t for t in timers if t["id"] == timer_id), None)
    assert timer is not None
    assert timer["schedule"] is None


# ============================================================
# 활성 타이머 조회 E2E 테스트 (REST API)
# ============================================================

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
    timer_data = create_timer_via_websocket(
        e2e_client,
        schedule_id=schedule_id,
        title="활성 타이머",
        allocated_duration=1800,
    )
    timer_id = timer_data["id"]

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

    # 2. 타이머 생성 후 일시정지 (WebSocket)
    timer_data = create_timer_via_websocket(
        e2e_client,
        schedule_id=schedule_id,
        title="일시정지 타이머",
        allocated_duration=1800,
    )
    timer_id = timer_data["id"]
    pause_timer_via_websocket(e2e_client, timer_id)

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

    # 2. 타이머 생성 후 종료 (WebSocket)
    timer_data = create_timer_via_websocket(
        e2e_client,
        schedule_id=schedule_id,
        allocated_duration=1800,
    )
    timer_id = timer_data["id"]
    stop_timer_via_websocket(e2e_client, timer_id)

    # 3. 사용자 활성 타이머 조회 (404 반환)
    response = e2e_client.get("/v1/timers/active")
    assert response.status_code == 404


@pytest.mark.e2e
def test_get_user_active_timer_with_include_schedule_e2e(e2e_client):
    """활성 타이머 조회 시 include_schedule 옵션 E2E 테스트"""
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

    # 2. Schedule에 연결된 타이머 생성 (RUNNING 상태)
    timer_data = create_timer_via_websocket(
        e2e_client,
        schedule_id=schedule_id,
        title="활성 include_schedule 테스트 타이머",
        allocated_duration=1800,
    )
    timer_id = timer_data["id"]

    # 3. include_schedule=True로 활성 타이머 조회
    response = e2e_client.get(
        "/v1/timers/active",
        params={"include_schedule": True}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == timer_id
    assert data["schedule"] is not None
    assert data["schedule"]["id"] == schedule_id
    assert data["schedule"]["title"] == schedule_title

    # 4. include_schedule=False로 활성 타이머 조회
    response = e2e_client.get(
        "/v1/timers/active",
        params={"include_schedule": False}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == timer_id
    assert data["schedule"] is None


# ============================================================
# 타이머 타임존 E2E 테스트 (REST API)
# ============================================================

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

    # 2. 타이머 생성 (WebSocket)
    timer_data = create_timer_via_websocket(
        e2e_client,
        schedule_id=schedule_id,
        allocated_duration=1800,
    )
    timer_id = timer_data["id"]

    # 3. 타이머 조회 (타임존 포함)
    get_response = e2e_client.get(
        f"/v1/timers/{timer_id}",
        params={"timezone": "+09:00"},
    )
    assert get_response.status_code == 200
    get_data = get_response.json()
    if get_data.get("started_at"):
        assert "+0900" in get_data["started_at"] or get_data["started_at"].endswith("+0900")


# ============================================================
# 일정의 타이머 조회 E2E 테스트 (REST API)
# ============================================================

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

    # 2. 여러 타이머 생성 (WebSocket)
    timer_ids = []
    for i in range(3):
        timer_data = create_timer_via_websocket(
            e2e_client,
            schedule_id=schedule_id,
            title=f"타이머 {i + 1}",
            allocated_duration=1800 * (i + 1),
        )
        timer_ids.append(timer_data["id"])

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
def test_get_schedule_active_timer_e2e(e2e_client):
    """일정의 활성 타이머 조회 E2E 테스트"""
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
    timer_data = create_timer_via_websocket(
        e2e_client,
        schedule_id=schedule_id,
        allocated_duration=1800,
    )
    timer_id = timer_data["id"]

    # 3. 활성 타이머 조회
    response = e2e_client.get(f"/v1/schedules/{schedule_id}/timers/active")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == timer_id
    assert data["status"] in ["running", "paused"]


@pytest.mark.e2e
def test_get_schedule_active_timer_not_found_e2e(e2e_client):
    """일정에 활성 타이머가 없을 때 404 반환 E2E 테스트"""
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

    # 2. 타이머 생성 후 종료 (WebSocket)
    timer_data = create_timer_via_websocket(
        e2e_client,
        schedule_id=schedule_id,
        allocated_duration=1800,
    )
    timer_id = timer_data["id"]
    stop_timer_via_websocket(e2e_client, timer_id)

    # 3. 활성 타이머 조회 (404 반환)
    response = e2e_client.get(f"/v1/schedules/{schedule_id}/timers/active")
    assert response.status_code == 404


# ============================================================
# 태그 관련 E2E 테스트 (REST API)
# ============================================================

@pytest.mark.e2e
def test_get_timer_with_tag_include_mode_none_e2e(e2e_client):
    """타이머 조회 시 tag_include_mode=none일 때 tags가 빈 배열인지 테스트"""
    # 1. 일정 생성
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

    # 3. 타이머 생성 시 태그 설정 (WebSocket)
    timer_data = create_timer_via_websocket(
        e2e_client,
        schedule_id=schedule_id,
        allocated_duration=1800,
        tag_ids=[tag_id],
    )
    timer_id = timer_data["id"]

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
    # 1. 일정 생성
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

    # 3. 타이머 생성 시 태그 설정 (WebSocket)
    timer_data = create_timer_via_websocket(
        e2e_client,
        schedule_id=schedule_id,
        allocated_duration=1800,
        tag_ids=[tag_id],
    )
    timer_id = timer_data["id"]

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


# ============================================================
# Todo 연결 타이머 E2E 테스트 (REST API)
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

    # 3. Todo 연결 타이머 생성 (WebSocket)
    todo_timer_data = create_timer_via_websocket(
        e2e_client,
        todo_id=todo_id,
        title="Todo 연결 타이머",
        allocated_duration=1800,
    )
    todo_timer_id = todo_timer_data["id"]

    # 4. 독립 타이머 생성 (WebSocket)
    independent_data = create_timer_via_websocket(
        e2e_client,
        title="독립 타이머",
        allocated_duration=600,
    )
    independent_id = independent_data["id"]

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

    # 3. Todo 연결 타이머 생성 (WebSocket)
    create_timer_via_websocket(
        e2e_client,
        todo_id=todo_id,
        title="include_todo 테스트 타이머",
        allocated_duration=1800,
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
# 복합 필터링 E2E 테스트 (REST API)
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
    schedule_running_data = create_timer_via_websocket(
        e2e_client,
        schedule_id=schedule_id,
        title="Schedule Running 타이머",
        allocated_duration=1800,
    )
    schedule_running_id = schedule_running_data["id"]

    # 3. 독립 RUNNING 타이머
    independent_data = create_timer_via_websocket(
        e2e_client,
        title="독립 Running 타이머",
        allocated_duration=600,
    )
    independent_id = independent_data["id"]

    # 4. Schedule 연결 COMPLETED 타이머
    schedule_completed_data = create_timer_via_websocket(
        e2e_client,
        schedule_id=schedule_id,
        title="Schedule Completed 타이머",
        allocated_duration=1800,
    )
    schedule_completed_id = schedule_completed_data["id"]
    stop_timer_via_websocket(e2e_client, schedule_completed_id)

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

    # 2. 타이머 생성 (WebSocket)
    timer_data = create_timer_via_websocket(
        e2e_client,
        schedule_id=schedule_id,
        title="모든 옵션 테스트 타이머",
        allocated_duration=1800,
    )
    timer_id = timer_data["id"]

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


# ============================================================
# API 일관성 E2E 테스트
# ============================================================

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

    # 2. RUNNING 타이머 생성 (WebSocket)
    timer_data = create_timer_via_websocket(
        e2e_client,
        schedule_id=schedule_id,
        title="활성 타이머",
        allocated_duration=1800,
    )
    timer_id = timer_data["id"]

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


# ============================================================
# 날짜 필터링 E2E 테스트
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

    # 2. 타이머 생성 (WebSocket)
    timer_data = create_timer_via_websocket(
        e2e_client,
        schedule_id=schedule_id,
        title="날짜 필터 테스트 타이머",
        allocated_duration=1800,
    )
    timer_id = timer_data["id"]

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

    # 2. 타이머 생성 (WebSocket)
    create_timer_via_websocket(
        e2e_client,
        schedule_id=schedule_id,
        title="미래 날짜 필터 테스트 타이머",
        allocated_duration=1800,
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
