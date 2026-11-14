"""게스트 이름 찾기와 생성 (service.lookup, service.create)

게스트 이름(정규형)은 guest.name에 있고 리소스 안에서 겹치지 않는다. handle은 "<게스트 행 id>@guest.invalid"다.
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
    return GuestCreate(
        resource_type=resource_type, resource_id=resource, name=name, password=password, turnstile_token="t"
    )


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
    assert handle == f"{row.id}@guest.invalid"
    assert row.name == "민수"


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
async def test_name_given_in_other_form_is_taken(kratos, resource):
    """다른 형태로 받은 이름도 정규형으로 저장하고 비교한다"""
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
async def test_name_comes_from_guest_row_not_kratos_trait(kratos, resource):
    """찾기와 중복 판정은 guest.name을 쓴다. Kratos trait만 바뀌어도 따라가지 않는다"""
    created = await service.create(_create(resource, name="민수"))
    [row] = guest_rows()
    kratos.identities[row.identity_id]["traits"]["name"] = "철수"

    assert (await service.lookup(_lookup(resource, name="민수"))).handle == created.handle
    assert (await service.lookup(_lookup(resource, name="철수"))).handle is None
    with pytest.raises(GuestNameTakenError):
        await service.create(_create(resource, name="민수"))


@pytest.mark.asyncio
async def test_name_taken_between_check_and_insert_is_409_and_removes_identity(kratos, resource, monkeypatch):
    """확인 뒤 같은 이름의 게스트가 먼저 저장되면 UNIQUE 제약으로 거절하고 만든 identity를 지운다"""
    from app.core import kratos_admin

    original = kratos_admin.create_identity
    competitor = []

    async def create_then_race(*args, **kwargs):
        identity = await original(*args, **kwargs)
        competitor.append(make_guest(kratos, resource, name="민수"))
        return identity

    monkeypatch.setattr(kratos_admin, "create_identity", create_then_race)
    with pytest.raises(GuestNameTakenError):
        await service.create(_create(resource, name="민수"))

    [row] = guest_rows()
    assert row.id == competitor[0].id
    assert list(kratos.identities) == [competitor[0].identity_id]
    assert len(kratos.deleted) == 1


@pytest.mark.asyncio
async def test_discarded_guests_name_is_free_again(kratos, resource):
    created = await service.create(_create(resource))
    [row] = guest_rows()
    await service.discard_guest(row.identity_id)

    assert (await service.lookup(_lookup(resource))).handle is None
    again = await service.create(_create(resource))
    assert again.guest_id != created.guest_id


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
async def test_lookup_does_not_cross_resources(kratos, host, resource):
    other = uuid.uuid4()
    host.statuses[other] = GuestHostStatus.OPEN
    await service.create(_create(resource))
    assert (await service.lookup(_lookup(other))).handle is None


@pytest.mark.asyncio
async def test_lookup_creates_nothing_and_does_not_call_kratos(kratos, resource):
    make_guest(kratos, resource, name="영희")
    kratos.down.add("admin")
    assert (await service.lookup(_lookup(resource, name="영희"))).handle
    assert (await service.lookup(_lookup(resource))).handle is None
    assert len(guest_rows()) == 1
    assert kratos.list_requests == []


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
async def test_admin_down_is_unavailable_and_creates_nothing(kratos, resource):
    kratos.down.add("admin")
    with pytest.raises(GuestServiceUnavailableError):
        await service.create(_create(resource))
    assert guest_rows() == []

@pytest.mark.asyncio
async def test_identity_creation_failure_leaves_nothing(kratos, resource):
    kratos.fail_create = True
    with pytest.raises(GuestServiceUnavailableError):
        await service.create(_create(resource))
    assert guest_rows() == []
    assert kratos.identities == {}


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
