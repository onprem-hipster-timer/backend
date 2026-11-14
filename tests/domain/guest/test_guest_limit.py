"""리소스당 게스트 수 상한 (service.MAX_GUESTS_PER_RESOURCE = 100)"""
import uuid

import pytest

from app.domain.guest import service
from app.domain.guest.host import GuestHostStatus
from tests.domain.guest.helpers import guest_rows, make_guest

CREATE = "/v1/guests"
LOOKUP = "/v1/guests/lookup"


@pytest.fixture
def resource(host):
    resource_id = uuid.uuid4()
    host.statuses[resource_id] = GuestHostStatus.OPEN
    return resource_id


def _body(resource, name, password="1234") -> dict:
    return {
        "resource_type": "meeting",
        "resource_id": str(resource),
        "name": name,
        "password": password,
        "turnstile_token": "t",
    }


def _fill(kratos, resource, count):
    return [make_guest(kratos, resource, name=f"g{i}") for i in range(count)]


def test_limit_is_100():
    assert service.MAX_GUESTS_PER_RESOURCE == 100


def test_hundredth_guest_is_created_and_next_is_409(guest_client, kratos, turnstile, resource):
    _fill(kratos, resource, 99)
    assert guest_client.post(CREATE, json=_body(resource, "백번째")).status_code == 201
    identities, verifications = len(kratos.identities), len(turnstile.requests)

    r = guest_client.post(CREATE, json=_body(resource, "넘침"))

    assert r.status_code == 409
    assert r.json()["error_type"] == "GuestLimitReachedError"
    assert r.json()["message"] == "이 리소스에는 게스트를 더 만들 수 없습니다"
    assert len(guest_rows()) == 100
    assert len(kratos.identities) == identities
    assert len(turnstile.requests) == verifications


def test_taken_name_on_full_resource_is_name_taken(guest_client, kratos, turnstile, resource):
    _fill(kratos, resource, 100)
    r = guest_client.post(CREATE, json=_body(resource, "g7"))
    assert r.status_code == 409
    assert r.json()["error_type"] == "GuestNameTakenError"
    assert turnstile.requests == []


def test_other_resource_is_not_affected(guest_client, kratos, host, resource):
    _fill(kratos, resource, 100)
    other = uuid.uuid4()
    host.statuses[other] = GuestHostStatus.OPEN
    assert guest_client.post(CREATE, json=_body(other, "g0")).status_code == 201


@pytest.mark.asyncio
async def test_discarding_a_guest_frees_a_slot(guest_client, kratos, resource):
    guests = _fill(kratos, resource, 100)
    assert guest_client.post(CREATE, json=_body(resource, "새 게스트")).status_code == 409

    await service.discard_guest(guests[0].identity_id)

    assert guest_client.post(CREATE, json=_body(resource, "새 게스트")).status_code == 201
    assert len(guest_rows()) == 100


def test_lookup_login_and_rename_work_on_full_resource(guest_client, kratos, resource):
    guests = _fill(kratos, resource, 100)
    handle = kratos.identities[guests[3].identity_id]["traits"]["handle"]

    found = guest_client.post(LOOKUP, json={"resource_type": "meeting", "resource_id": str(resource), "name": "g3"})
    assert found.json() == {"handle": handle}

    flow = guest_client.get("/auth/self-service/login/api").json()["id"]
    login = guest_client.post(
        f"/auth/self-service/login?flow={flow}",
        json={"method": "password", "identifier": handle, "password": "1234"},
    )
    assert login.status_code == 200
    token = login.json()["session_token"]

    rename = guest_client.post(
        "/auth/self-service/settings?flow=f1",
        json={"method": "profile", "traits": {"handle": handle, "name": "바뀐 이름"}},
        headers={"X-Session-Token": token},
    )
    assert rename.status_code == 200
    renamed = guest_client.post(
        LOOKUP, json={"resource_type": "meeting", "resource_id": str(resource), "name": "바뀐 이름"}
    )
    assert renamed.json() == {"handle": handle}
