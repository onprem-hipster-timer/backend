"""게스트 엔드포인트 (POST /v1/guests/enter, DELETE /v1/guests/me)와 플래그"""
import uuid

import pytest

from app.domain.guest.host import GuestHostStatus
from tests.domain.guest.helpers import guest_rows, make_guest

ENTER = "/v1/guests/enter"
ME = "/v1/guests/me"


@pytest.fixture
def resource(host):
    resource_id = uuid.uuid4()
    host.statuses[resource_id] = GuestHostStatus.OPEN
    return resource_id


def _body(resource, name="민수", password="1234", resource_type="meeting") -> dict:
    return {"resource_type": resource_type, "resource_id": str(resource), "name": name, "password": password}


def test_enter_returns_session_token_and_guest(guest_client, kratos, resource):
    r = guest_client.post(ENTER, json=_body(resource))

    assert r.status_code == 200, r.text
    [row] = guest_rows()
    assert r.json() == {
        "session_token": f"token-{row.identity_id}",
        "guest_id": str(row.id),
        "resource_type": "meeting",
        "resource_id": str(resource),
    }


def test_enter_needs_no_token(guest_client, resource):
    assert guest_client.post(ENTER, json=_body(resource)).status_code == 200


def test_enter_again_returns_same_guest(guest_client, resource):
    first = guest_client.post(ENTER, json=_body(resource)).json()
    again = guest_client.post(ENTER, json=_body(resource)).json()
    assert again["guest_id"] == first["guest_id"]


def test_enter_closed_resource_is_403(guest_client, host):
    resource = uuid.uuid4()
    host.statuses[resource] = GuestHostStatus.CLOSED
    r = guest_client.post(ENTER, json=_body(resource))
    assert r.status_code == 403


@pytest.mark.parametrize("status", [GuestHostStatus.EXPIRED, GuestHostStatus.MISSING, None])
def test_enter_unusable_resource_gives_same_refusal(guest_client, host, status):
    """없는 리소스와 기간이 끝난 리소스, 받지 않는 리소스는 같은 응답이다"""
    resource = uuid.uuid4()
    if status is not None:
        host.statuses[resource] = status
    closed = uuid.uuid4()
    host.statuses[closed] = GuestHostStatus.CLOSED

    r = guest_client.post(ENTER, json=_body(resource))
    closed_r = guest_client.post(ENTER, json=_body(closed))

    assert r.status_code == closed_r.status_code == 403
    assert r.json()["message"] == closed_r.json()["message"]


def test_enter_unregistered_resource_type_is_403(guest_client):
    assert guest_client.post(ENTER, json=_body(uuid.uuid4(), resource_type="todo")).status_code == 403


def test_eleventh_same_name_is_409(guest_client, resource):
    for i in range(10):
        assert guest_client.post(ENTER, json=_body(resource, password=f"p{i}")).status_code == 200
    assert guest_client.post(ENTER, json=_body(resource, password="other")).status_code == 409


def test_kratos_down_is_503(guest_client, kratos, resource):
    kratos.down.add("admin")
    assert guest_client.post(ENTER, json=_body(resource)).status_code == 503
    assert guest_rows() == []


@pytest.mark.parametrize("name", ["", "   ", "a" * 51, "민\x07수", "\n"])
def test_invalid_name_is_422(guest_client, kratos, resource, name):
    assert guest_client.post(ENTER, json=_body(resource, name=name)).status_code == 422
    assert kratos.identities == {}


@pytest.mark.parametrize("name", ["a", "a" * 50, "  민수  ", "김 민수", "🙂"])
def test_valid_names(guest_client, resource, name):
    assert guest_client.post(ENTER, json=_body(resource, name=name)).status_code == 200


@pytest.mark.parametrize("password", ["", "가" * 25, "a" * 73])
def test_invalid_password_is_422(guest_client, kratos, resource, password):
    """비어 있거나 UTF-8로 72바이트를 넘는 비밀번호 (가 25자 = 75바이트)"""
    assert guest_client.post(ENTER, json=_body(resource, password=password)).status_code == 422
    assert kratos.identities == {}


@pytest.mark.parametrize("password", ["1", " ", "a" * 72, "가" * 24, "1234"])
def test_any_short_password_is_accepted(guest_client, kratos, resource, password):
    r = guest_client.post(ENTER, json=_body(resource, password=password))
    assert r.status_code == 200
    assert kratos.passwords[guest_rows()[0].identity_id] == password


@pytest.mark.parametrize("field", ["resource_type", "resource_id", "name", "password"])
def test_missing_field_is_422(guest_client, resource, field):
    body = _body(resource)
    del body[field]
    assert guest_client.post(ENTER, json=body).status_code == 422


def test_unknown_resource_type_is_422(guest_client, resource):
    assert guest_client.post(ENTER, json=_body(resource, resource_type="planet")).status_code == 422


# ============ 자기 삭제 ============

def test_guest_deletes_itself(guest_client, kratos, tokens, resource, guest_events):
    guest = make_guest(kratos, resource)

    r = guest_client.delete(ME, headers=tokens.guest(guest.identity_id))

    assert r.status_code == 204
    assert guest_rows() == []
    assert kratos.deleted == [guest.identity_id]
    assert len(guest_events) == 1
    # 같은 JWT로 다시 불러도 행이 없으므로 아무것도 남지 않는다
    assert guest_client.delete(ME, headers=tokens.guest(guest.identity_id)).status_code == 204


def test_self_delete_needs_guest_token(guest_client, kratos, tokens, resource):
    guest = make_guest(kratos, resource)
    assert guest_client.delete(ME).status_code == 401
    assert guest_client.delete(ME, headers=tokens.member()).status_code == 403
    assert len(guest_rows()) == 1


def test_self_delete_of_closed_resource_guest_is_allowed(guest_client, kratos, host, tokens):
    resource = uuid.uuid4()
    host.statuses[resource] = GuestHostStatus.CLOSED
    guest = make_guest(kratos, resource)
    assert guest_client.delete(ME, headers=tokens.guest(guest.identity_id)).status_code == 204
    assert guest_rows() == []


# ============ 플래그 ============

def test_flag_off_endpoints_are_404(guest_client, guest_off, kratos, tokens, resource):
    guest = make_guest(kratos, resource)
    guest_off()

    assert guest_client.post(ENTER, json=_body(resource)).status_code == 404
    assert guest_client.post(ENTER, json={}).status_code == 404
    assert guest_client.delete(ME, headers=tokens.guest(guest.identity_id)).status_code == 404
    assert len(guest_rows()) == 1


def test_flag_off_guest_token_is_refused_on_member_routes(guest_client, guest_off, tokens):
    guest_off()
    assert guest_client.get("/v1/users/me", headers=tokens.guest("g-1")).status_code == 403
    # 클레임이 없는 회원 토큰은 플래그가 꺼져 있으면 받는다
    legacy = tokens.make("member-2", None, email="m2@example.com", email_verified=True)
    assert guest_client.get("/v1/users/me", headers={"Authorization": f"Bearer {legacy}"}).status_code == 200


def test_flag_on_token_without_schema_id_is_401(guest_client, tokens):
    legacy = tokens.make("member-2", None, email="m2@example.com", email_verified=True)
    assert guest_client.get("/v1/users/me", headers={"Authorization": f"Bearer {legacy}"}).status_code == 401
    assert guest_client.get("/v1/users/me", headers=tokens.member()).status_code == 200


def test_guest_token_is_refused_on_member_route(guest_client, kratos, tokens, resource):
    guest = make_guest(kratos, resource)
    r = guest_client.get("/v1/users/me", headers=tokens.guest(guest.identity_id))
    assert r.status_code == 403
