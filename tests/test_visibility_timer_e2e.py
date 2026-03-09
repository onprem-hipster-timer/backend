"""
Visibility - Timer 도메인 E2E 테스트

Timer 접근권한 설정 및 접근 제어 통합 테스트

Note: 타이머는 REST로 생성할 수 없으므로 WebSocket을 통해 생성합니다.
      UserBoundClient는 websocket_connect를 노출하지 않으므로
      _set_user_override() 호출 후 내부 클라이언트를 사용합니다.
"""
import pytest

from tests.conftest import timer_ws_client


def _make_timer(client):
    """
    WebSocket을 통해 타이머를 생성하고 ID를 반환합니다.

    e2e_client (TestClient) 또는 UserBoundClient 모두 지원합니다.
    """
    if hasattr(client, "_set_user_override"):
        # UserBoundClient: WS 연결 전에 사용자 override를 명시적으로 설정
        client._set_user_override()
        raw_client = client._client
    else:
        raw_client = client

    with timer_ws_client(raw_client) as ws:
        timer_data = ws.create_timer(
            title="테스트 타이머",
            allocated_duration=1800,
        )
    return timer_data["id"]


@pytest.mark.e2e
def test_set_and_get_visibility_timer(e2e_client):
    """Timer 접근권한 설정 및 조회 E2E 테스트"""
    timer_id = _make_timer(e2e_client)

    vis_response = e2e_client.put(
        f"/v1/visibility/timer/{timer_id}",
        json={"level": "friends"},
    )
    assert vis_response.status_code == 200
    vis_data = vis_response.json()
    assert vis_data["level"] == "friends"
    assert vis_data["resource_type"] == "timer"
    assert vis_data["resource_id"] == timer_id

    get_response = e2e_client.get(f"/v1/visibility/timer/{timer_id}")
    assert get_response.status_code == 200
    assert get_response.json()["level"] == "friends"


@pytest.mark.e2e
def test_set_visibility_allowed_emails_timer(e2e_client):
    """Timer ALLOWED_EMAILS 접근권한 설정 E2E 테스트"""
    timer_id = _make_timer(e2e_client)

    vis_response = e2e_client.put(
        f"/v1/visibility/timer/{timer_id}",
        json={
            "level": "allowed_emails",
            "allowed_emails": ["alice@example.com"],
            "allowed_domains": ["company.com"],
        },
    )
    assert vis_response.status_code == 200
    data = vis_response.json()
    assert data["level"] == "allowed_emails"
    assert "alice@example.com" in data["allowed_emails"]
    assert "company.com" in data["allowed_domains"]


@pytest.mark.e2e
def test_timer_visibility_public_access(multi_user_e2e):
    """전체 공개 Timer는 다른 사용자도 REST로 조회 가능 E2E 테스트"""
    client_a = multi_user_e2e.as_user("user-a")
    client_b = multi_user_e2e.as_user("user-b")

    timer_id = _make_timer(client_a)
    client_a.put(f"/v1/visibility/timer/{timer_id}", json={"level": "public"})

    response = client_b.get(f"/v1/timers/{timer_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == timer_id
    assert data["is_shared"] is True


@pytest.mark.e2e
def test_timer_visibility_private_blocks_access(multi_user_e2e):
    """비공개(기본) Timer는 소유자 외 조회 불가 E2E 테스트"""
    client_a = multi_user_e2e.as_user("user-a")
    client_b = multi_user_e2e.as_user("user-b")

    timer_id = _make_timer(client_a)
    # 접근권한 미설정 → PRIVATE (기본값)

    response = client_b.get(f"/v1/timers/{timer_id}")
    assert response.status_code == 403
