"""게스트 접근 정책, 폐기, 리소스 게스트 일괄 폐기, 게스트 권한 확인

정책: OPEN 허용 / CLOSED 거부(게스트 유지) / EXPIRED·MISSING 거부 후 폐기(행·identity 삭제, GuestDiscarded).
"""
import logging
import uuid

import pytest

from app.domain.guest import service
from app.domain.guest.events import GuestDiscarded
from app.domain.guest.exceptions import GuestAccessDeniedError
from app.domain.guest.host import GuestHostStatus, host_status, unregister_guest_host
from app.models.visibility import ResourceType
from app.shared.events import EventOrigin
from tests.domain.guest.helpers import guest_rows, make_guest

pytestmark = pytest.mark.usefixtures("guest_db")


@pytest.mark.asyncio
async def test_open_allows_and_keeps_guest(kratos, host, guest_events):
    resource = uuid.uuid4()
    host.statuses[resource] = GuestHostStatus.OPEN
    guest = make_guest(kratos, resource)

    assert await service.check_access(guest) is True
    assert [g.id for g in guest_rows()] == [guest.id]
    assert kratos.deleted == []
    assert guest_events == []


@pytest.mark.asyncio
async def test_closed_refuses_and_keeps_guest(kratos, host, guest_events):
    resource = uuid.uuid4()
    host.statuses[resource] = GuestHostStatus.CLOSED
    guest = make_guest(kratos, resource)

    assert await service.check_access(guest) is False
    assert [g.id for g in guest_rows()] == [guest.id]
    assert guest.identity_id in kratos.identities
    assert guest_events == []


@pytest.mark.parametrize("status", [GuestHostStatus.EXPIRED, GuestHostStatus.MISSING])
@pytest.mark.asyncio
async def test_expired_or_missing_refuses_and_discards(kratos, host, guest_events, status):
    resource = uuid.uuid4()
    host.statuses[resource] = status
    guest = make_guest(kratos, resource)
    other = make_guest(kratos, resource, name="다른 게스트")

    assert await service.check_access(guest) is False
    assert [g.id for g in guest_rows()] == [other.id]
    assert kratos.deleted == [guest.identity_id]
    assert guest_events == [GuestDiscarded(
        owner_id=guest.identity_id,
        origin=EventOrigin.GUEST,
        guest_id=guest.id,
        resource_type=ResourceType.MEETING,
        resource_id=resource,
    )]


@pytest.mark.asyncio
async def test_unregistered_resource_type_is_missing(kratos, guest_db, guest_events):
    """호스트를 등록하지 않은 리소스 종류의 게스트는 MISSING으로 보고 폐기한다"""
    unregister_guest_host(ResourceType.TODO)
    guest = make_guest(kratos, uuid.uuid4(), resource_type=ResourceType.TODO)

    from app.db.session import _session_manager
    with _session_manager.get_session() as session:
        assert host_status(session, ResourceType.TODO, guest.resource_id) == GuestHostStatus.MISSING
    assert await service.check_access(guest) is False
    assert guest_rows() == []
    assert len(guest_events) == 1


@pytest.mark.asyncio
async def test_discard_closes_access_even_when_kratos_is_down(kratos, host, guest_events, caplog, monkeypatch):
    # alembic 마이그레이션 테스트의 fileConfig가 이미 있던 로거를 끈다
    monkeypatch.setattr(service.logger, "disabled", False)
    resource = uuid.uuid4()
    host.statuses[resource] = GuestHostStatus.OPEN
    guest = make_guest(kratos, resource)
    kratos.down.add("admin")

    with caplog.at_level(logging.WARNING):
        assert await service.discard_guest(guest.identity_id) is True

    assert guest_rows() == []
    assert len(guest_events) == 1
    assert guest.identity_id in kratos.identities
    assert guest.identity_id in caplog.text
    with pytest.raises(GuestAccessDeniedError):
        await service.authorize(guest.identity_id, ResourceType.MEETING, resource)
    assert await service.login_allowed(guest.identity_id, "guest") is False


@pytest.mark.asyncio
async def test_discard_without_row_still_deletes_identity(kratos, guest_events):
    identity = kratos.add_identity("guest", {"handle": "h" * 36, "name": "x"})

    assert await service.discard_guest(identity["id"]) is False
    assert kratos.deleted == [identity["id"]]
    assert guest_events == []


@pytest.mark.asyncio
async def test_discard_twice_is_harmless(kratos, host, guest_events):
    guest = make_guest(kratos, uuid.uuid4())
    assert await service.discard_guest(guest.identity_id) is True
    assert await service.discard_guest(guest.identity_id) is False
    assert len(guest_events) == 1


@pytest.mark.asyncio
async def test_discard_resource_guests_removes_only_that_resource(kratos, host, guest_events):
    """이벤트를 게스트마다 처리하므로 한 번에 처리하는 이벤트 수 상한보다 게스트가 많아도 된다"""
    resource, other_resource = uuid.uuid4(), uuid.uuid4()
    guests = [make_guest(kratos, resource, name=f"g{i}") for i in range(12)]
    kept = make_guest(kratos, other_resource)

    assert await service.discard_resource_guests(ResourceType.MEETING, resource) == 12

    assert [g.id for g in guest_rows()] == [kept.id]
    assert sorted(kratos.deleted) == sorted(g.identity_id for g in guests)
    assert sorted(e.guest_id for e in guest_events) == sorted(g.id for g in guests)
    assert all(isinstance(e, GuestDiscarded) and e.resource_id == resource for e in guest_events)


@pytest.mark.asyncio
async def test_discard_resource_guests_without_guests(kratos, host):
    assert await service.discard_resource_guests(ResourceType.MEETING, uuid.uuid4()) == 0
    assert kratos.deleted == []


# ============ authorize (게스트 의존성이 쓰는 확인) ============

@pytest.mark.asyncio
async def test_authorize_returns_guest_of_open_resource(kratos, host):
    resource = uuid.uuid4()
    host.statuses[resource] = GuestHostStatus.OPEN
    guest = make_guest(kratos, resource)

    assert (await service.authorize(guest.identity_id, ResourceType.MEETING, resource)).id == guest.id


@pytest.mark.asyncio
async def test_authorize_refuses_other_resource(kratos, host):
    resource, other = uuid.uuid4(), uuid.uuid4()
    host.statuses[resource] = host.statuses[other] = GuestHostStatus.OPEN
    guest = make_guest(kratos, resource)

    with pytest.raises(GuestAccessDeniedError):
        await service.authorize(guest.identity_id, ResourceType.MEETING, other)
    with pytest.raises(GuestAccessDeniedError):
        await service.authorize(guest.identity_id, ResourceType.TODO, resource)
    assert len(guest_rows()) == 1


@pytest.mark.asyncio
async def test_authorize_refuses_unknown_identity(kratos, host):
    with pytest.raises(GuestAccessDeniedError):
        await service.authorize("no-such-identity", ResourceType.MEETING, uuid.uuid4())


@pytest.mark.asyncio
async def test_authorize_refuses_closed_and_keeps_guest(kratos, host):
    resource = uuid.uuid4()
    host.statuses[resource] = GuestHostStatus.CLOSED
    guest = make_guest(kratos, resource)

    with pytest.raises(GuestAccessDeniedError):
        await service.authorize(guest.identity_id, ResourceType.MEETING, resource)
    assert len(guest_rows()) == 1

    host.statuses[resource] = GuestHostStatus.OPEN
    assert (await service.authorize(guest.identity_id, ResourceType.MEETING, resource)).id == guest.id
