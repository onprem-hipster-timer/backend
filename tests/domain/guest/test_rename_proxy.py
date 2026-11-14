"""/auth 프록시의 게스트 이름 변경 (method: profile)

프록시는 같은 리소스의 다른 게스트가 쓰는 이름(정규형으로 비교)이면 Kratos에 넘기지 않고 409 guest_name_taken으로 답한다.
가짜 Kratos는 설정 제출 때 backend 설정 훅 판정(service.settings_change_allowed)을 거친다.
"""
import unicodedata
import uuid

import pytest

from app.domain.guest import service
from app.domain.guest.host import GuestHostStatus
from tests.domain.guest.helpers import make_guest

SETTINGS_SUBMIT = "/auth/self-service/settings?flow=f1"


@pytest.fixture
def resource(host):
    resource_id = uuid.uuid4()
    host.statuses[resource_id] = GuestHostStatus.OPEN
    return resource_id


def _session(kratos, guest) -> dict:
    token = f"token-{guest.identity_id}"
    kratos.sessions[token] = guest.identity_id
    return {"X-Session-Token": token}


def _rename(client, kratos, guest, name, **json_overrides):
    handle = kratos.identities[guest.identity_id]["traits"]["handle"]
    body = {"method": "profile", "traits": {"handle": handle, "name": name}, **json_overrides}
    return client.post(SETTINGS_SUBMIT, json=body, headers=_session(kratos, guest))


def test_guest_renames_through_proxy(guest_client, kratos, resource, guest_events):
    guest = make_guest(kratos, resource, name="민수")

    r = _rename(guest_client, kratos, guest, "철수")

    assert r.status_code == 200, r.text
    assert kratos.name_of(guest.identity_id) == "철수"
    assert [e.name for e in guest_events] == ["철수"]


def test_rename_to_taken_name_is_409_and_not_forwarded(guest_client, kratos, resource, guest_events):
    guest = make_guest(kratos, resource, name="민수")
    make_guest(kratos, resource, name="철수")

    r = _rename(guest_client, kratos, guest, "철수")

    assert r.status_code == 409
    assert r.json()["error"]["id"] == "guest_name_taken"
    assert kratos.name_of(guest.identity_id) == "민수"
    assert guest_events == []


def test_rename_to_name_stored_in_other_form_is_409(guest_client, kratos, resource):
    guest = make_guest(kratos, resource, name="민수")
    make_guest(kratos, resource, name=unicodedata.normalize("NFD", "철수"))
    assert _rename(guest_client, kratos, guest, "철수").status_code == 409


def test_name_key_is_read_ignoring_case(guest_client, kratos, resource):
    guest = make_guest(kratos, resource, name="민수")
    make_guest(kratos, resource, name="철수")
    handle = kratos.identities[guest.identity_id]["traits"]["handle"]

    r = guest_client.post(
        SETTINGS_SUBMIT,
        json={"method": "profile", "Traits": {"handle": handle, "NAME": "철수"}},
        headers=_session(kratos, guest),
    )
    assert r.status_code == 409


def test_form_encoded_rename_to_taken_name_is_409(guest_client, kratos, resource):
    guest = make_guest(kratos, resource, name="민수")
    make_guest(kratos, resource, name="철수")
    handle = kratos.identities[guest.identity_id]["traits"]["handle"]

    r = guest_client.post(
        SETTINGS_SUBMIT,
        data={"method": "profile", "traits.handle": handle, "traits.name": "철수"},
        headers=_session(kratos, guest),
    )
    assert r.status_code == 409


def test_rename_to_own_current_name_is_allowed(guest_client, kratos, resource, guest_events):
    guest = make_guest(kratos, resource, name="민수")
    make_guest(kratos, resource, name="철수")

    assert _rename(guest_client, kratos, guest, "민수").status_code == 200
    assert guest_events == []


def test_rename_to_name_used_in_other_resource_is_allowed(guest_client, kratos, resource):
    guest = make_guest(kratos, resource, name="민수")
    make_guest(kratos, uuid.uuid4(), name="철수")
    assert _rename(guest_client, kratos, guest, "철수").status_code == 200


@pytest.mark.asyncio
async def test_name_freed_by_discard_can_be_taken(guest_client, kratos, resource):
    guest = make_guest(kratos, resource, name="민수")
    other = make_guest(kratos, resource, name="철수")
    assert _rename(guest_client, kratos, guest, "철수").status_code == 409

    await service.discard_guest(other.identity_id)

    assert _rename(guest_client, kratos, guest, "철수").status_code == 200
    assert kratos.name_of(guest.identity_id) == "철수"


def test_invalid_name_is_left_to_settings_hook(guest_client, kratos, resource):
    guest = make_guest(kratos, resource, name="민수")
    r = _rename(guest_client, kratos, guest, 3)
    assert r.status_code == 400
    assert kratos.name_of(guest.identity_id) == "민수"


@pytest.mark.parametrize("name", ["김  민수", "김　민수", "철​수"])
def test_rename_to_non_canonical_name_is_not_stored(guest_client, kratos, resource, name):
    guest = make_guest(kratos, resource, name="민수")
    make_guest(kratos, resource, name="김 민수")

    r = _rename(guest_client, kratos, guest, name)

    assert r.status_code in (400, 409)
    assert kratos.name_of(guest.identity_id) == "민수"


def test_submitted_name_is_compared_in_canonical_form(guest_client, kratos, resource):
    guest = make_guest(kratos, resource, name="민수")
    make_guest(kratos, resource, name="김 민수")
    r = _rename(guest_client, kratos, guest, "김\u3000\u3000민수")
    assert r.status_code == 409
    assert r.json()["error"]["id"] == "guest_name_taken"


def test_proxy_check_does_not_call_kratos_admin(guest_client, kratos, resource):
    guest = make_guest(kratos, resource, name="민수")
    make_guest(kratos, resource, name="철수")
    kratos.down.add("admin")
    assert _rename(guest_client, kratos, guest, "철수").status_code == 409
    assert kratos.list_requests == []


def test_rename_through_proxy_updates_lookup(guest_client, kratos, resource):
    guest = make_guest(kratos, resource, name="민수")
    assert _rename(guest_client, kratos, guest, "철수").status_code == 200

    body = {"resource_type": "meeting", "resource_id": str(resource)}
    handle = kratos.identities[guest.identity_id]["traits"]["handle"]
    assert guest_client.post("/v1/guests/lookup", json={**body, "name": "철수"}).json() == {"handle": handle}
    assert guest_client.post("/v1/guests/lookup", json={**body, "name": "민수"}).json() == {"handle": None}
