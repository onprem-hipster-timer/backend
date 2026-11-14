"""Kratos 훅 수신 엔드포인트 (/internal/kratos/hooks/*)"""
import uuid

import pytest

import app.core.config as app_config
from app.domain.guest.events import GuestRenamed
from app.domain.guest.host import GuestHostStatus
from tests.domain.guest.conftest import HOOK_KEY
from tests.domain.guest.helpers import guest_rows, make_guest

LOGIN = "/internal/kratos/hooks/login"
SETTINGS = "/internal/kratos/hooks/settings/{}"
KEY = {"X-Kratos-Hook-Key": HOOK_KEY}


@pytest.fixture
def guest(kratos, host):
    resource = uuid.uuid4()
    host.statuses[resource] = GuestHostStatus.OPEN
    return make_guest(kratos, resource)


def _refusal_ids(response) -> list[int]:
    body = response.json()
    assert set(body) == {"messages"}
    [group] = body["messages"]
    assert group["instance_ptr"] == "#/"
    assert all(m["type"] == "error" and isinstance(m["text"], str) for m in group["messages"])
    return [m["id"] for m in group["messages"]]


# ============ 인증·플래그 ============

@pytest.mark.parametrize("path", [LOGIN, SETTINGS.format("profile")])
@pytest.mark.parametrize("headers", [{}, {"X-Kratos-Hook-Key": "wrong"}, {"X-Kratos-Hook-Key": ""}])
def test_missing_or_wrong_key_is_401(guest_client, path, headers):
    r = guest_client.post(path, json={"identity_id": "x", "schema_id": "default"}, headers=headers)
    assert r.status_code == 401


def test_empty_configured_key_refuses_every_request(guest_client, monkeypatch):
    monkeypatch.setattr(app_config.settings, "KRATOS_HOOK_API_KEY", "")
    r = guest_client.post(LOGIN, json={"identity_id": "x"}, headers={"X-Kratos-Hook-Key": ""})
    assert r.status_code == 401


@pytest.mark.parametrize("path", [LOGIN, SETTINGS.format("profile")])
def test_flag_off_is_404(guest_client, guest_off, path):
    guest_off()
    assert guest_client.post(path, json={"identity_id": "x"}, headers=KEY).status_code == 404


def test_hook_routes_are_not_in_openapi(guest_client):
    paths = guest_client.get("/openapi.json").json()["paths"]
    assert not any(p.startswith("/internal/") for p in paths)


def test_unknown_settings_method_is_422(guest_client):
    r = guest_client.post(SETTINGS.format("totp"), json={"identity_id": "x"}, headers=KEY)
    assert r.status_code == 422


def test_body_without_identity_id_is_422(guest_client):
    assert guest_client.post(LOGIN, json={"schema_id": "guest"}, headers=KEY).status_code == 422


# ============ 로그인 ============

def test_verified_member_is_allowed(guest_client):
    r = guest_client.post(LOGIN, json={"identity_id": "m", "schema_id": "default", "verified": True}, headers=KEY)
    assert r.status_code == 200
    assert r.json() == {}


def test_unverified_member_is_refused_with_unverified_message(guest_client):
    r = guest_client.post(LOGIN, json={"identity_id": "m", "schema_id": "default", "verified": False}, headers=KEY)
    assert r.status_code == 403
    assert _refusal_ids(r) == [4000010]


def test_guest_with_open_resource_is_allowed(guest_client, guest):
    r = guest_client.post(LOGIN, json={"identity_id": guest.identity_id, "schema_id": "guest"}, headers=KEY)
    assert r.status_code == 200


def test_guest_without_row_is_refused(guest_client, kratos):
    identity = kratos.add_identity("guest", {"handle": "h", "name": "x"})
    r = guest_client.post(LOGIN, json={"identity_id": identity["id"], "schema_id": "guest", "verified": True}, headers=KEY)
    assert r.status_code == 403
    assert _refusal_ids(r) == [4000001]


def test_guest_of_closed_resource_is_refused_and_kept(guest_client, host, guest):
    host.statuses[guest.resource_id] = GuestHostStatus.CLOSED
    r = guest_client.post(LOGIN, json={"identity_id": guest.identity_id, "schema_id": "guest"}, headers=KEY)
    assert r.status_code == 403
    assert len(guest_rows()) == 1


def test_guest_of_expired_resource_is_refused_and_discarded(guest_client, host, kratos, guest, guest_events):
    host.statuses[guest.resource_id] = GuestHostStatus.EXPIRED
    r = guest_client.post(LOGIN, json={"identity_id": guest.identity_id, "schema_id": "guest"}, headers=KEY)
    assert r.status_code == 403
    assert guest_rows() == []
    assert kratos.deleted == [guest.identity_id]
    assert len(guest_events) == 1


# ============ 설정 ============

def _settings(guest_client, method, identity_id, schema_id, traits):
    body = {"identity_id": identity_id, "schema_id": schema_id, "traits": traits}
    return guest_client.post(SETTINGS.format(method), json=body, headers=KEY)


def test_guest_rename_is_allowed_and_published(guest_client, kratos, guest, guest_events):
    traits = {**kratos.identities[guest.identity_id]["traits"], "name": "철수"}
    r = _settings(guest_client, "profile", guest.identity_id, "guest", traits)
    assert r.status_code == 200
    assert r.json() == {}
    assert [type(e) for e in guest_events] == [GuestRenamed]
    assert guest_events[0].name == "철수"


def test_guest_identifier_change_is_refused(guest_client, kratos, guest, guest_events):
    traits = {"handle": str(uuid.uuid4()), "name": "철수"}
    r = _settings(guest_client, "profile", guest.identity_id, "guest", traits)
    assert r.status_code == 403
    assert _refusal_ids(r) == [4000001]
    assert guest_events == []


@pytest.mark.parametrize("method", ["password", "oidc"])
def test_guest_password_and_external_login_are_refused(guest_client, kratos, guest, method):
    traits = kratos.identities[guest.identity_id]["traits"]
    r = _settings(guest_client, method, guest.identity_id, "guest", traits)
    assert r.status_code == 403


@pytest.mark.parametrize("method", ["profile", "password", "oidc"])
def test_member_settings_are_allowed(guest_client, method):
    r = _settings(guest_client, method, "member", "default", {"email": "m@example.com"})
    assert r.status_code == 200
