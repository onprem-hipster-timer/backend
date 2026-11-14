"""게스트 입장 (service.enter)

이름이 같고 비밀번호가 맞는 게스트가 있으면 다시 들어가고, 없으면 새 게스트를 만든다.
"""
import uuid

import pytest

from app.domain.guest import service
from app.domain.guest.exceptions import (
    GuestEntryRefusedError,
    GuestNameLimitError,
    GuestServiceUnavailableError,
)
from app.domain.guest.host import GuestHostStatus
from app.domain.guest.schema.dto import GuestEnter
from app.models.visibility import ResourceType
from tests.domain.guest.helpers import guest_rows, make_guest

pytestmark = pytest.mark.usefixtures("guest_db")


def _enter(resource, name="민수", password="1234", resource_type=ResourceType.MEETING) -> GuestEnter:
    return GuestEnter(resource_type=resource_type, resource_id=resource, name=name, password=password)


@pytest.fixture
def resource(host):
    resource_id = uuid.uuid4()
    host.statuses[resource_id] = GuestHostStatus.OPEN
    return resource_id


@pytest.mark.asyncio
async def test_first_enter_creates_guest(kratos, resource):
    result = await service.enter(_enter(resource, password="1"))

    [row] = guest_rows()
    assert result.guest_id == row.id
    assert (result.resource_type, result.resource_id) == (ResourceType.MEETING, resource)
    assert result.session_token == f"token-{row.identity_id}"
    identity = kratos.identities[row.identity_id]
    assert identity["schema_id"] == "guest"
    assert identity["traits"]["name"] == "민수"
    handle = identity["traits"]["handle"]
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
    await service.enter(_enter(resource, password="a"))
    await service.enter(_enter(resource, password="b"))
    handles = {i["traits"]["handle"] for i in kratos.identities.values()}
    assert len(handles) == 2


@pytest.mark.asyncio
async def test_enter_again_with_same_name_and_password(kratos, resource):
    first = await service.enter(_enter(resource))
    again = await service.enter(_enter(resource))

    assert again.guest_id == first.guest_id
    assert len(guest_rows()) == 1


@pytest.mark.asyncio
async def test_name_is_trimmed_before_matching(kratos, resource):
    first = await service.enter(_enter(resource, name="민수"))
    again = await service.enter(_enter(resource, name="  민수 "))
    assert again.guest_id == first.guest_id


@pytest.mark.asyncio
async def test_same_name_other_password_creates_second_guest(kratos, resource):
    first = await service.enter(_enter(resource, password="1234"))
    second = await service.enter(_enter(resource, password="5678"))

    assert second.guest_id != first.guest_id
    assert len(guest_rows()) == 2
    # 둘 다 자기 비밀번호로 다시 들어간다
    assert (await service.enter(_enter(resource, password="1234"))).guest_id == first.guest_id
    assert (await service.enter(_enter(resource, password="5678"))).guest_id == second.guest_id


@pytest.mark.asyncio
async def test_same_password_other_name_creates_second_guest(kratos, resource):
    first = await service.enter(_enter(resource, name="민수"))
    second = await service.enter(_enter(resource, name="영희"))
    assert second.guest_id != first.guest_id


@pytest.mark.asyncio
async def test_same_name_and_password_in_other_resource_is_other_guest(kratos, host, resource):
    other = uuid.uuid4()
    host.statuses[other] = GuestHostStatus.OPEN
    first = await service.enter(_enter(resource))
    second = await service.enter(_enter(other))
    assert second.guest_id != first.guest_id


@pytest.mark.asyncio
async def test_name_is_read_from_kratos(kratos, resource):
    """Kratos에서 이름을 바꾼 게스트는 바뀐 이름으로 다시 들어간다"""
    first = await service.enter(_enter(resource, name="민수"))
    [row] = guest_rows()
    kratos.identities[row.identity_id]["traits"]["name"] = "철수"

    assert (await service.enter(_enter(resource, name="철수"))).guest_id == first.guest_id
    assert (await service.enter(_enter(resource, name="민수"))).guest_id != first.guest_id


@pytest.mark.asyncio
async def test_identities_are_read_in_one_batched_call(kratos, resource):
    for i in range(3):
        make_guest(kratos, resource, name=f"g{i}")
    kratos.list_requests.clear()

    await service.enter(_enter(resource, name="g1", password="1234"))

    assert len(kratos.list_requests) == 1
    assert len(kratos.list_requests[0].url.params.get_list("ids")) == 3


@pytest.mark.asyncio
async def test_eleventh_guest_with_same_name_is_refused(kratos, resource):
    for i in range(service.MAX_GUESTS_PER_NAME):
        await service.enter(_enter(resource, password=f"pw-{i}"))
    assert len(guest_rows()) == 10

    with pytest.raises(GuestNameLimitError):
        await service.enter(_enter(resource, password="pw-new"))
    assert len(guest_rows()) == 10
    assert len(kratos.identities) == 10
    # 이미 있는 게스트는 계속 들어간다
    await service.enter(_enter(resource, password="pw-9"))
    # 다른 이름은 만들 수 있다
    await service.enter(_enter(resource, name="다른 이름", password="pw-new"))
    assert len(guest_rows()) == 11


@pytest.mark.parametrize("status", [GuestHostStatus.CLOSED, GuestHostStatus.EXPIRED, GuestHostStatus.MISSING])
@pytest.mark.asyncio
async def test_resource_not_open_refuses_entry(kratos, host, status):
    resource = uuid.uuid4()
    host.statuses[resource] = status

    with pytest.raises(GuestEntryRefusedError):
        await service.enter(_enter(resource))
    assert guest_rows() == []
    assert kratos.identities == {}


@pytest.mark.asyncio
async def test_unregistered_resource_type_refuses_entry(kratos, host):
    with pytest.raises(GuestEntryRefusedError):
        await service.enter(_enter(uuid.uuid4(), resource_type=ResourceType.TODO))
    assert kratos.identities == {}


@pytest.mark.asyncio
async def test_closed_resource_keeps_guests_expired_discards_them(kratos, host, guest_events):
    resource = uuid.uuid4()
    guest = make_guest(kratos, resource)

    host.statuses[resource] = GuestHostStatus.CLOSED
    with pytest.raises(GuestEntryRefusedError):
        await service.enter(_enter(resource))
    assert [g.id for g in guest_rows()] == [guest.id]

    host.statuses[resource] = GuestHostStatus.EXPIRED
    with pytest.raises(GuestEntryRefusedError):
        await service.enter(_enter(resource))
    assert guest_rows() == []
    assert kratos.deleted == [guest.identity_id]
    assert len(guest_events) == 1


# ============ Kratos 실패 ============

@pytest.mark.asyncio
async def test_identity_creation_failure_leaves_nothing(kratos, resource):
    kratos.fail_create = True
    with pytest.raises(GuestServiceUnavailableError):
        await service.enter(_enter(resource))
    assert guest_rows() == []
    assert kratos.identities == {}


@pytest.mark.parametrize("failure", ["public_down", "login_500", "login_refused"])
@pytest.mark.asyncio
async def test_login_failure_after_creation_removes_guest_and_identity(kratos, resource, guest_events, failure):
    if failure == "public_down":
        kratos.down.add("public")
    elif failure == "login_500":
        kratos.login_status = 502
    else:
        kratos.login_status = 403

    with pytest.raises(GuestServiceUnavailableError):
        await service.enter(_enter(resource))

    assert guest_rows() == []
    assert kratos.identities == {}
    assert len(kratos.deleted) == 1
    assert guest_events == []


@pytest.mark.asyncio
async def test_login_failure_with_identity_deletion_failure_leaves_no_usable_guest(kratos, resource):
    """identity 삭제도 실패하면 identity는 남지만 게스트 행이 없어 로그인 훅이 거부한다"""
    kratos.down.add("public")
    original_admin = kratos.admin

    def admin(request):
        if request.method == "DELETE":
            kratos.down.add("admin")
        return original_admin(request)

    kratos.admin = admin
    with pytest.raises(GuestServiceUnavailableError):
        await service.enter(_enter(resource))

    [leftover] = kratos.identities.values()
    assert guest_rows() == []
    assert await service.login_allowed(leftover["id"], "guest") is False


@pytest.mark.asyncio
async def test_identity_lookup_failure_is_unavailable(kratos, resource):
    await service.enter(_enter(resource))
    kratos.fail_list = True
    with pytest.raises(GuestServiceUnavailableError):
        await service.enter(_enter(resource))
    assert len(guest_rows()) == 1


@pytest.mark.asyncio
async def test_kratos_down_on_reenter_is_unavailable_and_creates_nothing(kratos, resource):
    await service.enter(_enter(resource))
    kratos.down.add("public")
    with pytest.raises(GuestServiceUnavailableError):
        await service.enter(_enter(resource))
    assert len(guest_rows()) == 1
    assert len(kratos.identities) == 1
