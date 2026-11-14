"""게스트를 받는 경로의 의존성 (require_guest_access, get_current_guest)

테스트 전용 라우트 GET /test/meetings/{meeting_id}로 확인한다.
"""
import uuid

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.error_handlers import register_exception_handlers
from app.domain.guest import service
from app.domain.guest.dependencies import require_guest_access
from app.domain.guest.host import GuestHostStatus
from app.domain.guest.model import Guest
from app.models.visibility import ResourceType
from tests.domain.guest.helpers import guest_rows, make_guest


@pytest.fixture
def client(guest_client):
    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/test/meetings/{meeting_id}")
    async def meeting_for_guest(guest: Guest = Depends(require_guest_access(ResourceType.MEETING, "meeting_id"))):
        return {"guest_id": str(guest.id)}

    @test_app.get("/test/wrong-param/{meeting_id}")
    async def wrong_param(guest: Guest = Depends(require_guest_access(ResourceType.MEETING, "other_id"))):
        return {}

    return TestClient(test_app)


@pytest.fixture
def setup(kratos, host):
    resource = uuid.uuid4()
    host.statuses[resource] = GuestHostStatus.OPEN
    return resource, make_guest(kratos, resource)


def _get(client, resource, headers=None):
    return client.get(f"/test/meetings/{resource}", headers=headers or {})


def test_guest_of_resource_passes(client, tokens, setup):
    resource, guest = setup
    r = _get(client, resource, tokens.guest(guest.identity_id))
    assert r.status_code == 200
    assert r.json() == {"guest_id": str(guest.id)}


def test_guest_of_other_resource_is_refused(client, tokens, host, setup):
    _, guest = setup
    other = uuid.uuid4()
    host.statuses[other] = GuestHostStatus.OPEN
    assert _get(client, other, tokens.guest(guest.identity_id)).status_code == 403


def test_member_token_is_refused(client, tokens, setup):
    resource, _ = setup
    assert _get(client, resource, tokens.member()).status_code == 403


def test_token_without_schema_id_is_refused(client, tokens, setup):
    resource, guest = setup
    token = tokens.make(guest.identity_id, None)
    assert _get(client, resource, {"Authorization": f"Bearer {token}"}).status_code == 403


def test_no_token_is_401(client, setup):
    resource, _ = setup
    assert _get(client, resource).status_code == 401


@pytest.mark.asyncio
async def test_discarded_guest_with_valid_jwt_is_refused(client, tokens, setup):
    resource, guest = setup
    headers = tokens.guest(guest.identity_id)
    assert _get(client, resource, headers).status_code == 200

    await service.discard_guest(guest.identity_id)

    assert _get(client, resource, headers).status_code == 403


def test_closed_refuses_and_keeps_guest(client, tokens, host, setup):
    resource, guest = setup
    headers = tokens.guest(guest.identity_id)
    host.statuses[resource] = GuestHostStatus.CLOSED
    assert _get(client, resource, headers).status_code == 403
    assert len(guest_rows()) == 1

    host.statuses[resource] = GuestHostStatus.OPEN
    assert _get(client, resource, headers).status_code == 200


def test_expired_refuses_and_discards(client, tokens, host, kratos, setup, guest_events):
    resource, guest = setup
    host.statuses[resource] = GuestHostStatus.EXPIRED
    assert _get(client, resource, tokens.guest(guest.identity_id)).status_code == 403
    assert guest_rows() == []
    assert kratos.deleted == [guest.identity_id]
    assert len(guest_events) == 1


def test_flag_off_refuses_guest(client, tokens, guest_off, setup):
    resource, guest = setup
    guest_off()
    assert _get(client, resource, tokens.guest(guest.identity_id)).status_code == 403


def test_invalid_resource_id_is_refused(client, tokens, setup):
    _, guest = setup
    assert client.get("/test/meetings/not-a-uuid", headers=tokens.guest(guest.identity_id)).status_code == 403


def test_missing_path_param_is_refused(client, tokens, setup):
    resource, guest = setup
    r = client.get(f"/test/wrong-param/{resource}", headers=tokens.guest(guest.identity_id))
    assert r.status_code == 403
