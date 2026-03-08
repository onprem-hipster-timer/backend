"""
Visibility - Schedule 도메인 E2E 테스트

스케줄 가시성 설정 및 접근 제어 통합 테스트
"""
import pytest


@pytest.mark.e2e
def test_set_and_get_visibility_schedule(e2e_client):
    """스케줄 가시성 설정 및 조회 E2E 테스트"""
    schedule_id = e2e_client.post(
        "/v1/schedules",
        json={"title": "가시성 테스트 일정", "start_time": "2024-01-01T10:00:00Z", "end_time": "2024-01-01T12:00:00Z"},
    ).json()["id"]

    vis_response = e2e_client.put(
        f"/v1/visibility/schedule/{schedule_id}",
        json={"level": "public"},
    )
    assert vis_response.status_code == 200
    vis_data = vis_response.json()
    assert vis_data["level"] == "public"
    assert vis_data["resource_type"] == "schedule"
    assert vis_data["resource_id"] == schedule_id

    get_response = e2e_client.get(f"/v1/visibility/schedule/{schedule_id}")
    assert get_response.status_code == 200
    assert get_response.json()["level"] == "public"


@pytest.mark.e2e
def test_set_visibility_allowed_emails_schedule(e2e_client):
    """스케줄 ALLOWED_EMAILS 가시성 - 이메일/도메인 목록 포함 E2E 테스트"""
    schedule_id = e2e_client.post(
        "/v1/schedules",
        json={"title": "이메일 공개 일정", "start_time": "2024-01-01T10:00:00Z", "end_time": "2024-01-01T12:00:00Z"},
    ).json()["id"]

    vis_response = e2e_client.put(
        f"/v1/visibility/schedule/{schedule_id}",
        json={
            "level": "allowed_emails",
            "allowed_emails": ["alice@example.com", "bob@example.com"],
            "allowed_domains": ["company.com"],
        },
    )
    assert vis_response.status_code == 200
    data = vis_response.json()
    assert data["level"] == "allowed_emails"
    assert "alice@example.com" in data["allowed_emails"]
    assert "bob@example.com" in data["allowed_emails"]
    assert "company.com" in data["allowed_domains"]


@pytest.mark.e2e
def test_schedule_visibility_friends_scope_shared(multi_user_e2e):
    """친구에게 공유된 일정이 scope=shared로 조회되는지 E2E 테스트"""
    client_a = multi_user_e2e.as_user("user-a")
    client_b = multi_user_e2e.as_user("user-b")

    schedule_response = client_a.post(
        "/v1/schedules",
        json={"title": "친구 공개 일정", "start_time": "2024-01-01T10:00:00Z", "end_time": "2024-01-01T12:00:00Z"},
    )
    assert schedule_response.status_code == 201
    schedule_id = schedule_response.json()["id"]

    vis_response = client_a.put(f"/v1/visibility/schedule/{schedule_id}", json={"level": "friends"})
    assert vis_response.status_code == 200

    friend_request = client_a.post(
        "/v1/friends/requests",
        json={"addressee_id": multi_user_e2e.get_user("user-b").sub},
    )
    assert friend_request.status_code == 201

    pending_response = client_b.get("/v1/friends/requests/received")
    assert pending_response.status_code == 200
    friendship_id = pending_response.json()[0]["id"]
    accept_response = client_b.post(f"/v1/friends/requests/{friendship_id}/accept")
    assert accept_response.status_code == 200

    shared_response = client_b.get(
        "/v1/schedules",
        params={"start_date": "2024-01-01T00:00:00Z", "end_date": "2024-01-01T23:59:59Z", "scope": "shared"},
    )
    assert shared_response.status_code == 200
    shared_schedules = shared_response.json()
    shared_ids = [s["id"] for s in shared_schedules]
    assert schedule_id in shared_ids

    shared_schedule = next(s for s in shared_schedules if s["id"] == schedule_id)
    assert shared_schedule["is_shared"] is True
    assert shared_schedule["owner_id"] == multi_user_e2e.get_user("user-a").sub


@pytest.mark.e2e
def test_schedule_visibility_friends_single_item_access(multi_user_e2e):
    """친구가 공유된 일정을 단건 조회할 수 있는지 E2E 테스트"""
    client_a = multi_user_e2e.as_user("user-a")
    client_b = multi_user_e2e.as_user("user-b")

    schedule_response = client_a.post(
        "/v1/schedules",
        json={"title": "친구 공개 일정", "start_time": "2024-01-01T10:00:00Z", "end_time": "2024-01-01T12:00:00Z"},
    )
    assert schedule_response.status_code == 201
    schedule_id = schedule_response.json()["id"]

    client_a.put(f"/v1/visibility/schedule/{schedule_id}", json={"level": "friends"})

    client_a.post("/v1/friends/requests", json={"addressee_id": multi_user_e2e.get_user("user-b").sub})
    friendship_id = client_b.get("/v1/friends/requests/received").json()[0]["id"]
    client_b.post(f"/v1/friends/requests/{friendship_id}/accept")

    get_response = client_b.get(f"/v1/schedules/{schedule_id}")
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["id"] == schedule_id
    assert data["is_shared"] is True


@pytest.mark.e2e
def test_schedule_visibility_non_friend_cannot_access(multi_user_e2e):
    """친구가 아닌 사용자는 친구 공개 일정에 접근 불가 E2E 테스트"""
    client_a = multi_user_e2e.as_user("user-a")
    client_c = multi_user_e2e.as_user("user-c")

    schedule_response = client_a.post(
        "/v1/schedules",
        json={"title": "친구 공개 일정", "start_time": "2024-01-01T10:00:00Z", "end_time": "2024-01-01T12:00:00Z"},
    )
    assert schedule_response.status_code == 201
    schedule_id = schedule_response.json()["id"]
    client_a.put(f"/v1/visibility/schedule/{schedule_id}", json={"level": "friends"})

    shared_response = client_c.get(
        "/v1/schedules",
        params={"start_date": "2024-01-01T00:00:00Z", "end_date": "2024-01-01T23:59:59Z", "scope": "shared"},
    )
    assert shared_response.status_code == 200
    assert schedule_id not in [s["id"] for s in shared_response.json()]

    assert client_c.get(f"/v1/schedules/{schedule_id}").status_code == 403


@pytest.mark.e2e
def test_schedule_visibility_selected_friends(multi_user_e2e):
    """선택된 친구에게만 공유되는 일정 E2E 테스트"""
    client_a = multi_user_e2e.as_user("user-a")
    client_b = multi_user_e2e.as_user("user-b")
    client_c = multi_user_e2e.as_user("user-c")

    user_b_id = multi_user_e2e.get_user("user-b").sub
    user_c_id = multi_user_e2e.get_user("user-c").sub

    client_a.post("/v1/friends/requests", json={"addressee_id": user_b_id})
    client_b.post(f"/v1/friends/requests/{client_b.get('/v1/friends/requests/received').json()[0]['id']}/accept")

    client_a.post("/v1/friends/requests", json={"addressee_id": user_c_id})
    client_c.post(f"/v1/friends/requests/{client_c.get('/v1/friends/requests/received').json()[0]['id']}/accept")

    schedule_response = client_a.post(
        "/v1/schedules",
        json={"title": "선택 친구 공개 일정", "start_time": "2024-01-01T10:00:00Z", "end_time": "2024-01-01T12:00:00Z"},
    )
    assert schedule_response.status_code == 201
    schedule_id = schedule_response.json()["id"]
    client_a.put(
        f"/v1/visibility/schedule/{schedule_id}",
        json={"level": "selected", "allowed_user_ids": [user_b_id]},
    )

    params = {"start_date": "2024-01-01T00:00:00Z", "end_date": "2024-01-01T23:59:59Z", "scope": "shared"}
    assert schedule_id in [s["id"] for s in client_b.get("/v1/schedules", params=params).json()]
    assert schedule_id not in [s["id"] for s in client_c.get("/v1/schedules", params=params).json()]


@pytest.mark.e2e
def test_schedule_visibility_public(multi_user_e2e):
    """전체 공개 일정 E2E 테스트"""
    client_a = multi_user_e2e.as_user("user-a")
    client_c = multi_user_e2e.as_user("user-c")

    schedule_response = client_a.post(
        "/v1/schedules",
        json={"title": "전체 공개 일정", "start_time": "2024-01-01T10:00:00Z", "end_time": "2024-01-01T12:00:00Z"},
    )
    assert schedule_response.status_code == 201
    schedule_id = schedule_response.json()["id"]
    client_a.put(f"/v1/visibility/schedule/{schedule_id}", json={"level": "public"})

    shared_ids = [s["id"] for s in client_c.get(
        "/v1/schedules",
        params={"start_date": "2024-01-01T00:00:00Z", "end_date": "2024-01-01T23:59:59Z", "scope": "shared"},
    ).json()]
    assert schedule_id in shared_ids
    assert client_c.get(f"/v1/schedules/{schedule_id}").status_code == 200


@pytest.mark.e2e
def test_schedule_scope_all(multi_user_e2e):
    """scope=all로 내 일정 + 공유 일정 모두 조회 E2E 테스트"""
    client_a = multi_user_e2e.as_user("user-a")
    client_b = multi_user_e2e.as_user("user-b")

    schedule_a = client_a.post(
        "/v1/schedules",
        json={"title": "A의 공개 일정", "start_time": "2024-01-01T10:00:00Z", "end_time": "2024-01-01T12:00:00Z"},
    )
    schedule_a_id = schedule_a.json()["id"]
    client_a.put(f"/v1/visibility/schedule/{schedule_a_id}", json={"level": "public"})

    schedule_b = client_b.post(
        "/v1/schedules",
        json={"title": "B의 일정", "start_time": "2024-01-01T14:00:00Z", "end_time": "2024-01-01T16:00:00Z"},
    )
    schedule_b_id = schedule_b.json()["id"]

    all_response = client_b.get(
        "/v1/schedules",
        params={"start_date": "2024-01-01T00:00:00Z", "end_date": "2024-01-01T23:59:59Z", "scope": "all"},
    )
    assert all_response.status_code == 200
    all_ids = [s["id"] for s in all_response.json()]
    assert schedule_a_id in all_ids
    assert schedule_b_id in all_ids
