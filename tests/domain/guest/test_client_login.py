"""게스트가 회원처럼 /auth 프록시로 Kratos에 로그인한다 (생성 → handle 찾기 → 비밀번호 로그인 → whoami)

가짜 Kratos는 로그인 때 backend 로그인 훅 판정(service.login_allowed)을 거친다.
"""
import uuid

import pytest

from app.domain.guest.host import GuestHostStatus


@pytest.fixture
def resource(host):
    resource_id = uuid.uuid4()
    host.statuses[resource_id] = GuestHostStatus.OPEN
    return resource_id


def _login(client, identifier: str, password: str):
    flow = client.get("/auth/self-service/login/api").json()["id"]
    return client.post(
        f"/auth/self-service/login?flow={flow}",
        json={"method": "password", "identifier": identifier, "password": password},
    )


def _create_and_find(client, resource, name="민수", password="1234") -> str:
    body = {"resource_type": "meeting", "resource_id": str(resource), "name": name}
    assert client.post("/v1/guests", json={**body, "password": password, "turnstile_token": "t"}).status_code == 201
    return client.post("/v1/guests/lookup", json=body).json()["handle"]


def test_guest_logs_in_with_handle_through_auth_proxy(guest_client, resource):
    handle = _create_and_find(guest_client, resource)

    r = _login(guest_client, handle, "1234")

    assert r.status_code == 200, r.text
    token = r.json()["session_token"]
    whoami = guest_client.get("/auth/sessions/whoami?tokenize_as=api", headers={"X-Session-Token": token})
    assert whoami.status_code == 200
    assert whoami.json()["identity"]["traits"] == {"handle": handle, "name": "민수"}


def test_wrong_password_is_refused_by_kratos(guest_client, resource):
    handle = _create_and_find(guest_client, resource)
    r = _login(guest_client, handle, "4321")
    assert r.status_code == 400


def test_login_is_refused_when_resource_closes(guest_client, host, resource):
    handle = _create_and_find(guest_client, resource)
    host.statuses[resource] = GuestHostStatus.CLOSED
    assert _login(guest_client, handle, "1234").status_code == 400
