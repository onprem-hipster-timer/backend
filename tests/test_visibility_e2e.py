"""
Visibility API 기본 동작 E2E 테스트

/v1/visibility/{resource_type}/{resource_id} 공통 API 동작 검증:
소유권 강제, 리소스 미존재, 설정 변경/삭제 lifecycle
"""
from uuid import uuid4

import pytest


def _make_schedule(client):
    return client.post(
        "/v1/schedules",
        json={"title": "테스트 일정", "start_time": "2024-01-01T10:00:00Z", "end_time": "2024-01-01T12:00:00Z"},
    ).json()["id"]


@pytest.mark.e2e
def test_update_visibility(e2e_client):
    """접근권한 설정 변경 (friends → public) E2E 테스트"""
    schedule_id = _make_schedule(e2e_client)

    e2e_client.put(f"/v1/visibility/schedule/{schedule_id}", json={"level": "friends"})

    update_response = e2e_client.put(
        f"/v1/visibility/schedule/{schedule_id}",
        json={"level": "public"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["level"] == "public"


@pytest.mark.e2e
def test_delete_visibility(e2e_client):
    """접근권한 삭제 후 GET은 404 E2E 테스트"""
    schedule_id = _make_schedule(e2e_client)
    e2e_client.put(f"/v1/visibility/schedule/{schedule_id}", json={"level": "public"})

    delete_response = e2e_client.delete(f"/v1/visibility/schedule/{schedule_id}")
    assert delete_response.status_code == 200

    get_response = e2e_client.get(f"/v1/visibility/schedule/{schedule_id}")
    assert get_response.status_code == 404


@pytest.mark.e2e
def test_get_visibility_not_set_returns_404(e2e_client):
    """접근권한 미설정 리소스 조회 시 404 E2E 테스트"""
    schedule_id = _make_schedule(e2e_client)
    response = e2e_client.get(f"/v1/visibility/schedule/{schedule_id}")
    assert response.status_code == 404


@pytest.mark.e2e
def test_set_visibility_resource_not_found(e2e_client):
    """존재하지 않는 리소스에 접근권한 설정 시 404 E2E 테스트"""
    non_existent_id = str(uuid4())
    response = e2e_client.put(
        f"/v1/visibility/schedule/{non_existent_id}",
        json={"level": "public"},
    )
    assert response.status_code == 404


@pytest.mark.e2e
def test_set_visibility_non_owner_denied(multi_user_e2e):
    """소유자가 아닌 사용자는 접근권한 설정 불가 (403) E2E 테스트"""
    client_a = multi_user_e2e.as_user("user-a")
    client_b = multi_user_e2e.as_user("user-b")

    schedule_id = _make_schedule(client_a)

    response = client_b.put(
        f"/v1/visibility/schedule/{schedule_id}",
        json={"level": "public"},
    )
    assert response.status_code == 403


@pytest.mark.e2e
def test_delete_visibility_non_owner_denied(multi_user_e2e):
    """소유자가 아닌 사용자는 접근권한 삭제 불가 (403) E2E 테스트"""
    client_a = multi_user_e2e.as_user("user-a")
    client_b = multi_user_e2e.as_user("user-b")

    schedule_id = _make_schedule(client_a)
    client_a.put(f"/v1/visibility/schedule/{schedule_id}", json={"level": "public"})

    response = client_b.delete(f"/v1/visibility/schedule/{schedule_id}")
    assert response.status_code == 403
