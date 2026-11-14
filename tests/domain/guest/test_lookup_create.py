"""게스트 이름 찾기와 생성 (service.lookup, service.create)

게스트 이름은 리소스 안에서 겹치지 않는다. 이름은 Kratos identity에만 있으므로 리소스 게스트의 identity를 읽어 비교한다.
"""
import unicodedata
import uuid

import pytest

from app.domain.guest import service
from app.domain.guest.exceptions import (
    GuestEntryRefusedError,
    GuestNameTakenError,
    GuestServiceUnavailableError,
)
from app.domain.guest.host import GuestHostStatus
from app.domain.guest.schema.dto import GuestCreate, GuestLookup
from app.models.visibility import ResourceType
from tests.domain.guest.helpers import guest_rows, make_guest

pytestmark = pytest.mark.usefixtures("guest_db")


def _create(resource, name="민수", password="1234", resource_type=ResourceType.MEETING) -> GuestCreate:
    return GuestCreate(resource_type=resource_type, resource_id=resource, name=name, password=password)


def _lookup(resource, name="민수", resource_type=ResourceType.MEETING) -> GuestLookup:
    return GuestLookup(resource_type=resource_type, resource_id=resource, name=name)


@pytest.fixture
def resource(host):
    resource_id = uuid.uuid4()
    host.statuses[resource_id] = GuestHostStatus.OPEN
    return resource_id


# ============ 생성 ============

@pytest.mark.asyncio
async def test_create_makes_identity_and_row(kratos, resource):
    result = await service.create(_create(resource, password="1"))

    [row] = guest_rows()
    assert result.guest_id == row.id
    assert (result.resource_type, result.resource_id) == (ResourceType.MEETING, resource)
    identity = kratos.identities[row.identity_id]
    assert identity["schema_id"] == "guest"
    assert identity["traits"]["name"] == "민수"
    handle = identity["traits"]["handle"]
    assert result.handle == handle
    local, domain = handle.split("@")
    uuid.UUID(local)
    assert domain == service.GUEST_HANDLE_DOMAIN == "guest.invalid"
    # Kratos의 require_verified_address를 통과하도록 handle을 인증된 주소로 만든다
    assert identity["verifiable_addresses"] == [
        {"value": handle, "via": "email", "verified": True, "status": "completed"}
    ]
    assert kratos.passwords[row.identity_id] == "1"


@pytest.mark.asyncio
async def test_each_guest_gets_its_own_handle(kratos, resource):
    first = await service.create(_create(resource, name="민수"))
    second = await service.create(_create(resource, name="영희"))
    assert first.handle != second.handle


@pytest.mark.asyncio
async def test_taken_name_is_409_and_leaves_nothing(kratos, resource):
    await service.create(_create(resource, password="1234"))

    with pytest.raises(GuestNameTakenError):
        await service.create(_create(resource, password="5678"))

    assert len(guest_rows()) == 1
    assert len(kratos.identities) == 1
    assert kratos.deleted == []


@pytest.mark.parametrize("variant", ["  민수 ", unicodedata.normalize("NFD", "민수")])
@pytest.mark.asyncio
async def test_name_is_compared_after_normalisation(kratos, resource, variant):
    assert variant != "민수"
    await service.create(_create(resource, name="민수"))
    with pytest.raises(GuestNameTakenError):
        await service.create(_create(resource, name=variant))


@pytest.mark.asyncio
async def test_name_stored_in_other_form_in_kratos_is_taken(kratos, resource):
    """Kratos에 NFC가 아닌 이름이 저장돼 있어도 NFC로 비교한다"""
    make_guest(kratos, resource, name=unicodedata.normalize("NFD", "민수"))
    with pytest.raises(GuestNameTakenError):
        await service.create(_create(resource, name="민수"))


@pytest.mark.asyncio
async def test_names_differing_in_case_are_different(kratos, resource):
    await service.create(_create(resource, name="Minsu"))
    await service.create(_create(resource, name="minsu"))
    assert len(guest_rows()) == 2


@pytest.mark.asyncio
async def test_same_name_in_other_resource_is_allowed(kratos, host, resource):
    other = uuid.uuid4()
    host.statuses[other] = GuestHostStatus.OPEN
    first = await service.create(_create(resource))
    second = await service.create(_create(other))
    assert second.guest_id != first.guest_id
    assert len(guest_rows()) == 2


@pytest.mark.asyncio
async def test_same_name_in_other_resource_type_is_allowed(kratos, host, resource):
    make_guest(kratos, resource, resource_type=ResourceType.TODO)
    await service.create(_create(resource))
    assert len(guest_rows()) == 2


@pytest.mark.asyncio
async def test_name_follows_renames_in_kratos(kratos, resource):
    """Kratos에서 이름을 바꾸면 옛 이름은 비고 새 이름은 차지된다"""
    await service.create(_create(resource, name="민수"))
    [row] = guest_rows()
    kratos.identities[row.identity_id]["traits"]["name"] = "철수"

    with pytest.raises(GuestNameTakenError):
        await service.create(_create(resource, name="철수"))
    await service.create(_create(resource, name="민수"))


@pytest.mark.asyncio
async def test_discarded_guests_name_is_free_again(kratos, resource):
    created = await service.create(_create(resource))
    [row] = guest_rows()
    await service.discard_guest(row.identity_id)

    assert (await service.lookup(_lookup(resource))).handle is None
    again = await service.create(_create(resource))
    assert again.guest_id != created.guest_id


@pytest.mark.asyncio
async def test_row_without_identity_does_not_hold_name(kratos, resource):
    """Kratos에서 identity가 사라진 게스트 행은 이름을 차지하지 않는다"""
    guest = make_guest(kratos, resource)
    del kratos.identities[guest.identity_id]
    await service.create(_create(resource))


@pytest.mark.asyncio
async def test_identities_are_read_in_one_batched_call(kratos, resource):
    for i in range(3):
        make_guest(kratos, resource, name=f"g{i}")
    kratos.list_requests.clear()

    await service.create(_create(resource, name="새 이름"))

    assert len(kratos.list_requests) == 1
    assert len(kratos.list_requests[0].url.params.get_list("ids")) == 3


@pytest.mark.asyncio
async def test_more_guests_than_one_batch_are_all_compared(kratos, resource, monkeypatch):
    from app.core import kratos_admin

    monkeypatch.setattr(kratos_admin, "IDENTITY_BATCH_SIZE", 2)
    for i in range(5):
        make_guest(kratos, resource, name=f"g{i}")
    kratos.list_requests.clear()

    with pytest.raises(GuestNameTakenError):
        await service.create(_create(resource, name="g4"))
    assert len(kratos.list_requests) == 3


# ============ 이름 찾기 ============

@pytest.mark.asyncio
async def test_lookup_finds_handle(kratos, resource):
    created = await service.create(_create(resource))
    found = await service.lookup(_lookup(resource, name=" 민수 "))
    assert found.handle == created.handle


@pytest.mark.asyncio
async def test_lookup_nfd_name_finds_nfc_guest(kratos, resource):
    created = await service.create(_create(resource, name="민수"))
    found = await service.lookup(_lookup(resource, name=unicodedata.normalize("NFD", "민수")))
    assert found.handle == created.handle


@pytest.mark.asyncio
async def test_lookup_without_match_has_no_handle(kratos, resource):
    await service.create(_create(resource, name="민수"))
    assert (await service.lookup(_lookup(resource, name="영희"))).handle is None


@pytest.mark.asyncio
async def test_lookup_in_empty_resource_does_not_call_kratos(kratos, resource):
    assert (await service.lookup(_lookup(resource))).handle is None
    assert kratos.list_requests == []


@pytest.mark.asyncio
async def test_lookup_does_not_cross_resources(kratos, host, resource):
    other = uuid.uuid4()
    host.statuses[other] = GuestHostStatus.OPEN
    await service.create(_create(resource))
    assert (await service.lookup(_lookup(other))).handle is None


@pytest.mark.asyncio
async def test_lookup_creates_nothing(kratos, resource):
    await service.lookup(_lookup(resource))
    assert guest_rows() == []
    assert kratos.identities == {}


# ============ 리소스 상태 ============

@pytest.mark.parametrize("call", ["create", "lookup"])
@pytest.mark.parametrize("status", [GuestHostStatus.CLOSED, GuestHostStatus.EXPIRED, GuestHostStatus.MISSING])
@pytest.mark.asyncio
async def test_resource_not_open_is_refused(kratos, host, status, call):
    resource = uuid.uuid4()
    host.statuses[resource] = status

    with pytest.raises(GuestEntryRefusedError):
        if call == "create":
            await service.create(_create(resource))
        else:
            await service.lookup(_lookup(resource))
    assert guest_rows() == []
    assert kratos.identities == {}


@pytest.mark.parametrize("call", ["create", "lookup"])
@pytest.mark.asyncio
async def test_unregistered_resource_type_is_refused(kratos, host, call):
    with pytest.raises(GuestEntryRefusedError):
        if call == "create":
            await service.create(_create(uuid.uuid4(), resource_type=ResourceType.TODO))
        else:
            await service.lookup(_lookup(uuid.uuid4(), resource_type=ResourceType.TODO))
    assert kratos.identities == {}


@pytest.mark.parametrize("call", ["create", "lookup"])
@pytest.mark.asyncio
async def test_closed_resource_keeps_guests_expired_and_missing_discard_them(kratos, host, guest_events, call):
    async def attempt(resource):
        with pytest.raises(GuestEntryRefusedError):
            if call == "create":
                await service.create(_create(resource, name="새 이름"))
            else:
                await service.lookup(_lookup(resource))

    resource = uuid.uuid4()
    guest = make_guest(kratos, resource)
    host.statuses[resource] = GuestHostStatus.CLOSED
    await attempt(resource)
    assert [g.id for g in guest_rows()] == [guest.id]
    assert kratos.deleted == []

    host.statuses[resource] = GuestHostStatus.EXPIRED
    await attempt(resource)
    assert guest_rows() == []
    assert kratos.deleted == [guest.identity_id]
    assert len(guest_events) == 1

    missing = uuid.uuid4()
    gone = make_guest(kratos, missing)
    await attempt(missing)
    assert guest_rows() == []
    assert kratos.deleted == [guest.identity_id, gone.identity_id]


# ============ Kratos 실패 ============

@pytest.mark.asyncio
async def test_identity_creation_failure_leaves_nothing(kratos, resource):
    kratos.fail_create = True
    with pytest.raises(GuestServiceUnavailableError):
        await service.create(_create(resource))
    assert guest_rows() == []
    assert kratos.identities == {}


@pytest.mark.asyncio
async def test_admin_down_is_unavailable_and_creates_nothing(kratos, resource):
    make_guest(kratos, resource, name="다른 이름")
    kratos.down.add("admin")
    with pytest.raises(GuestServiceUnavailableError):
        await service.create(_create(resource))
    with pytest.raises(GuestServiceUnavailableError):
        await service.lookup(_lookup(resource))
    assert len(guest_rows()) == 1


@pytest.mark.asyncio
async def test_identity_lookup_failure_is_unavailable_not_free(kratos, resource):
    """이름을 확인할 수 없으면 비어 있다고 보지 않는다"""
    await service.create(_create(resource))
    kratos.fail_list = True
    with pytest.raises(GuestServiceUnavailableError):
        await service.create(_create(resource, name="영희"))
    with pytest.raises(GuestServiceUnavailableError):
        await service.lookup(_lookup(resource))
    assert len(guest_rows()) == 1
    assert len(kratos.identities) == 1


@pytest.mark.asyncio
async def test_row_failure_after_identity_creation_removes_identity(kratos, resource, monkeypatch, guest_events):
    from app.crud import guest as crud

    def broken(session, guest):
        raise RuntimeError("db down")

    monkeypatch.setattr(crud, "create_guest", broken)
    with pytest.raises(RuntimeError):
        await service.create(_create(resource))

    assert guest_rows() == []
    assert kratos.identities == {}
    assert len(kratos.deleted) == 1
    assert guest_events == []
