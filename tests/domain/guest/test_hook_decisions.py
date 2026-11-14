"""Kratos 훅 판정 (service.login_allowed, service.settings_change_allowed)"""
import uuid

import pytest

from app.domain.guest import service
from app.domain.guest.events import GuestRenamed
from app.domain.guest.host import GuestHostStatus
from app.models.visibility import ResourceType
from app.shared.events import EventOrigin
from tests.domain.guest.helpers import guest_rows, make_guest

pytestmark = pytest.mark.usefixtures("guest_db")


@pytest.fixture
def open_guest(kratos, host):
    resource = uuid.uuid4()
    host.statuses[resource] = GuestHostStatus.OPEN
    return make_guest(kratos, resource)


# ============ 로그인 ============

@pytest.mark.parametrize("schema_id", ["default", None])
@pytest.mark.asyncio
async def test_member_login_needs_verified_address(kratos, schema_id):
    assert await service.login_allowed("member", schema_id, True) is True
    assert await service.login_allowed("member", schema_id, False) is False


@pytest.mark.asyncio
async def test_guest_login_with_open_resource(open_guest):
    assert await service.login_allowed(open_guest.identity_id, "guest", False) is True


@pytest.mark.asyncio
async def test_guest_login_ignores_verified_flag(kratos, host):
    """게스트는 주소 인증과 상관없이 게스트 행과 접근 정책으로만 정한다"""
    identity = kratos.add_identity("guest", {"handle": "h", "name": "x"})
    assert await service.login_allowed(identity["id"], "guest", True) is False


@pytest.mark.asyncio
async def test_guest_login_without_row_is_refused(kratos):
    identity = kratos.add_identity("guest", {"handle": "h", "name": "x"})
    assert await service.login_allowed(identity["id"], "guest", False) is False


@pytest.mark.asyncio
async def test_guest_login_closed_keeps_guest(kratos, host, open_guest):
    host.statuses[open_guest.resource_id] = GuestHostStatus.CLOSED
    assert await service.login_allowed(open_guest.identity_id, "guest", False) is False
    assert len(guest_rows()) == 1


@pytest.mark.asyncio
async def test_guest_login_expired_discards(kratos, host, open_guest, guest_events):
    host.statuses[open_guest.resource_id] = GuestHostStatus.EXPIRED
    assert await service.login_allowed(open_guest.identity_id, "guest", False) is False
    assert guest_rows() == []
    assert kratos.deleted == [open_guest.identity_id]


@pytest.mark.asyncio
async def test_guest_schema_id_follows_setting(kratos, host, open_guest, monkeypatch):
    import app.core.config as app_config

    monkeypatch.setattr(app_config.settings, "KRATOS_GUEST_SCHEMA_ID", "visitor")
    # "guest" schema는 이제 회원으로 보므로 주소 인증이 필요하다
    assert await service.login_allowed(open_guest.identity_id, "guest", False) is False
    assert await service.login_allowed(open_guest.identity_id, "visitor", False) is True


# ============ 설정 ============

def _traits(kratos, guest, **changes):
    return {**kratos.identities[guest.identity_id]["traits"], **changes}


@pytest.mark.parametrize("method", ["profile", "password", "oidc"])
@pytest.mark.asyncio
async def test_member_settings_are_allowed(kratos, method):
    assert await service.settings_change_allowed(method, "member", "default", {"email": "a@b.c"}) is True


@pytest.mark.asyncio
async def test_guest_rename_is_allowed_and_published(kratos, open_guest, guest_events):
    traits = _traits(kratos, open_guest, name="철수")

    assert await service.settings_change_allowed("profile", open_guest.identity_id, "guest", traits) is True
    assert guest_events == [GuestRenamed(
        owner_id=open_guest.identity_id,
        origin=EventOrigin.GUEST,
        guest_id=open_guest.id,
        resource_type=ResourceType.MEETING,
        resource_id=open_guest.resource_id,
        name="철수",
    )]


@pytest.mark.asyncio
async def test_guest_profile_without_name_change_publishes_nothing(kratos, open_guest, guest_events):
    traits = _traits(kratos, open_guest)
    assert await service.settings_change_allowed("profile", open_guest.identity_id, "guest", traits) is True
    assert guest_events == []


@pytest.mark.asyncio
async def test_guest_cannot_change_login_identifier(kratos, open_guest, guest_events):
    traits = _traits(kratos, open_guest, handle=str(uuid.uuid4()), name="철수")
    assert await service.settings_change_allowed("profile", open_guest.identity_id, "guest", traits) is False
    traits.pop("handle")
    assert await service.settings_change_allowed("profile", open_guest.identity_id, "guest", traits) is False
    assert guest_events == []


@pytest.mark.parametrize("name", ["", "   ", " 철수", "a" * 51, "철\x00수", None, 3])
@pytest.mark.asyncio
async def test_guest_rename_follows_name_rules(kratos, open_guest, name):
    traits = _traits(kratos, open_guest, name=name)
    assert await service.settings_change_allowed("profile", open_guest.identity_id, "guest", traits) is False


@pytest.mark.parametrize("method", ["password", "oidc", "totp", "unknown"])
@pytest.mark.asyncio
async def test_guest_other_settings_are_refused(kratos, open_guest, method):
    traits = _traits(kratos, open_guest)
    assert await service.settings_change_allowed(method, open_guest.identity_id, "guest", traits) is False


@pytest.mark.asyncio
async def test_guest_without_row_cannot_rename(kratos):
    identity = kratos.add_identity("guest", {"handle": "h", "name": "x"})
    traits = {"handle": "h", "name": "y"}
    assert await service.settings_change_allowed("profile", identity["id"], "guest", traits) is False


@pytest.mark.asyncio
async def test_guest_of_closed_resource_cannot_rename(kratos, host, open_guest):
    host.statuses[open_guest.resource_id] = GuestHostStatus.CLOSED
    traits = _traits(kratos, open_guest, name="철수")
    assert await service.settings_change_allowed("profile", open_guest.identity_id, "guest", traits) is False


@pytest.mark.asyncio
async def test_rename_refused_when_current_identity_cannot_be_read(kratos, open_guest):
    kratos.fail_get = True
    traits = _traits(kratos, open_guest, name="철수")
    assert await service.settings_change_allowed("profile", open_guest.identity_id, "guest", traits) is False
