"""
게스트 서비스

- 접근 정책(check_access): 모든 게스트 확인이 이 함수를 쓴다.
  OPEN이면 허용, CLOSED면 거부하고 게스트를 남긴다, EXPIRED·MISSING이면 거부하고 게스트를 폐기한다
- 폐기(discard_guest, discard_resource_guests): 게스트 행 삭제와 GuestDiscarded 이벤트를 커밋한 뒤
  Kratos identity를 지운다. identity 삭제가 실패해도 행이 없으므로 접근은 닫힌다
  (로그인 훅은 행이 없는 게스트 identity를 거부한다). 실패는 로그로 남긴다
- 입장(enter), Kratos 로그인 훅·설정 훅 판정(login_allowed, settings_change_allowed). 회원 로그인은 판정하지 않는다

DB는 요청 세션이 아니라 자기 세션으로 쓰고 바로 커밋한다. 거부 응답과 함께 폐기가 rollback되지 않게 하고,
Kratos 호출 동안 트랜잭션을 열어 두지 않는다 (로그인 중에 Kratos가 이 서버의 로그인 훅을 부른다).

테스트: tests/domain/guest/
"""
import logging
import unicodedata
from contextlib import contextmanager
from typing import Iterator
from uuid import UUID, uuid4

from sqlmodel import Session

import app.core.config as app_config
from app.core import kratos_admin, kratos_public
from app.crud import guest as crud
from app.db.session import _session_manager
from app.domain.guest.events import GuestDiscarded, GuestRenamed
from app.domain.guest.exceptions import (
    GuestAccessDeniedError,
    GuestEntryRefusedError,
    GuestNameLimitError,
    GuestServiceUnavailableError,
)
from app.domain.guest.host import GuestHostStatus, host_status
from app.domain.guest.model import Guest
from app.domain.guest.schema.dto import GuestEnter, GuestEnterRead, normalize_guest_name
from app.models.visibility import ResourceType
from app.shared.events import EventOrigin
from app.shared.uow import clear_events, collect_event, flush_and_dispatch_events

logger = logging.getLogger(__name__)

# 한 리소스에서 같은 이름을 쓸 수 있는 게스트 수 (입장 한 번에 시도하는 로그인 수의 상한)
MAX_GUESTS_PER_NAME = 10

# 게스트 로그인 식별자(handle) "<uuid4>@<이 도메인>"의 도메인. 예약된 TLD라 메일이 가지 않는다.
# handle은 Kratos require_verified_address를 통과하도록 인증된 주소로 만들고, 게스트에게 보여 주지 않는다
GUEST_HANDLE_DOMAIN = "guest.invalid"


@contextmanager
def _transaction() -> Iterator[Session]:
    """자기 세션. 블록이 끝나면 커밋하고, 예외면 rollback하고 이벤트 큐를 비운다"""
    with _session_manager.get_session() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            clear_events(session)
            raise


def _status(resource_type: ResourceType, resource_id: UUID) -> GuestHostStatus:
    with _session_manager.get_session() as session:
        return host_status(session, resource_type, resource_id)


def _get_guest(identity_id: str) -> Guest | None:
    with _session_manager.get_session() as session:
        return crud.get_guest_by_identity(session, identity_id)


def is_guest_schema(schema_id: str | None) -> bool:
    return schema_id is not None and schema_id == app_config.settings.KRATOS_GUEST_SCHEMA_ID


def _delete_with_event(session: Session, guest: Guest) -> None:
    event = GuestDiscarded(
        owner_id=guest.identity_id,
        origin=EventOrigin.GUEST,
        guest_id=guest.id,
        resource_type=guest.resource_type,
        resource_id=guest.resource_id,
    )
    crud.delete_guest(session, guest)
    collect_event(session, event)
    # 이벤트 하나씩 처리한다 (한 drain 루프의 이벤트 수 상한 MAX_DISPATCH_DEPTH)
    flush_and_dispatch_events(session)


async def _delete_identity(identity_id: str) -> None:
    if not await kratos_admin.delete_identity(identity_id):
        logger.warning("게스트 Kratos identity 삭제 실패 (게스트 행은 지웠다): identity_id=%s", identity_id)


# ============ 접근 정책과 폐기 ============

async def check_access(guest: Guest) -> bool:
    """게스트가 지금 자기 리소스에 접근할 수 있는지. EXPIRED·MISSING이면 게스트를 폐기한다"""
    status = _status(guest.resource_type, guest.resource_id)
    if status == GuestHostStatus.OPEN:
        return True
    if status in (GuestHostStatus.EXPIRED, GuestHostStatus.MISSING):
        await discard_guest(guest.identity_id)
    return False


async def discard_guest(identity_id: str) -> bool:
    """게스트를 폐기한다. 게스트 행이 있었으면 True. Kratos identity는 행이 없어도 지운다"""
    with _transaction() as session:
        guest = crud.get_guest_by_identity(session, identity_id)
        if guest is not None:
            _delete_with_event(session, guest)
    await _delete_identity(identity_id)
    return guest is not None


async def discard_resource_guests(resource_type: ResourceType, resource_id: UUID) -> int:
    """리소스의 게스트를 모두 폐기하고 그 수를 돌려준다. 리소스를 지운 뒤(커밋 뒤) 부른다"""
    with _transaction() as session:
        guests = crud.list_resource_guests(session, resource_type, resource_id)
        identity_ids = [guest.identity_id for guest in guests]
        for guest in guests:
            _delete_with_event(session, guest)
    for identity_id in identity_ids:
        await _delete_identity(identity_id)
    return len(identity_ids)


async def authorize(identity_id: str, resource_type: ResourceType, resource_id: UUID) -> Guest:
    """게스트 identity가 이 리소스에 접근할 수 있으면 게스트 행, 아니면 GuestAccessDeniedError"""
    guest = _get_guest(identity_id)
    if guest is None or guest.resource_type != resource_type or guest.resource_id != resource_id:
        raise GuestAccessDeniedError()
    if not await check_access(guest):
        raise GuestAccessDeniedError()
    return guest


# ============ 입장 ============

async def _login(handle: str, password: str) -> str | None:
    try:
        return await kratos_public.password_login(handle, password)
    except kratos_public.KratosUnavailableError:
        logger.warning("게스트 로그인 중 Kratos 공개 API 오류", exc_info=True)
        raise GuestServiceUnavailableError()


def _entered(guest_id: UUID, data: GuestEnter, token: str) -> GuestEnterRead:
    return GuestEnterRead(
        session_token=token,
        guest_id=guest_id,
        resource_type=data.resource_type,
        resource_id=data.resource_id,
    )


async def _same_name_guests(data: GuestEnter) -> list[tuple[Guest, str]]:
    """리소스에서 지금 Kratos 이름이 data.name과 같은 게스트와 그 로그인 식별자(handle), 만든 순서대로"""
    with _session_manager.get_session() as session:
        guests = crud.list_resource_guests(session, data.resource_type, data.resource_id)
    if not guests:
        return []
    identities = await kratos_admin.get_identities([guest.identity_id for guest in guests])
    if identities is None:
        raise GuestServiceUnavailableError()
    traits_by_id = {identity["id"]: identity.get("traits") or {} for identity in identities}
    matches = []
    for guest in guests:
        traits = traits_by_id.get(guest.identity_id, {})
        name = traits.get("name")
        # data.name은 NFC다. Kratos에 다른 형태로 저장된 이름도 같은 이름으로 본다
        if (
                isinstance(name, str)
                and unicodedata.normalize("NFC", name) == data.name
                and isinstance(traits.get("handle"), str)
        ):
            matches.append((guest, traits["handle"]))
    return matches


async def _remove_new_guest(guest_id: UUID | None, identity_id: str) -> None:
    """입장을 마치지 못한 새 게스트를 지운다. 리소스가 저장한 것이 없으므로 이벤트는 내지 않는다"""
    if guest_id is not None:
        with _transaction() as session:
            guest = session.get(Guest, guest_id)
            if guest is not None:
                crud.delete_guest(session, guest)
    await _delete_identity(identity_id)


async def _create_guest(data: GuestEnter) -> GuestEnterRead:
    handle = f"{uuid4()}@{GUEST_HANDLE_DOMAIN}"
    identity = await kratos_admin.create_identity(
        app_config.settings.KRATOS_GUEST_SCHEMA_ID,
        {"handle": handle, "name": data.name},
        data.password,
        verified_addresses=(handle,),
    )
    if identity is None:
        raise GuestServiceUnavailableError()
    identity_id = identity["id"]

    guest_id: UUID | None = None
    try:
        with _transaction() as session:
            guest = crud.create_guest(session, Guest.model_validate(data, update={"identity_id": identity_id}))
            guest_id = guest.id
        token = await _login(handle, data.password)
    except BaseException:
        await _remove_new_guest(guest_id, identity_id)
        raise
    if token is None:
        await _remove_new_guest(guest_id, identity_id)
        raise GuestServiceUnavailableError()
    return _entered(guest_id, data, token)


async def enter(data: GuestEnter) -> GuestEnterRead:
    """이름과 비밀번호가 맞는 게스트가 있으면 다시 들어가고, 없으면 새 게스트를 만든다"""
    status = _status(data.resource_type, data.resource_id)
    if status != GuestHostStatus.OPEN:
        if status in (GuestHostStatus.EXPIRED, GuestHostStatus.MISSING):
            await discard_resource_guests(data.resource_type, data.resource_id)
        raise GuestEntryRefusedError()

    candidates = await _same_name_guests(data)
    for guest, handle in candidates:
        token = await _login(handle, data.password)
        if token is not None:
            return _entered(guest.id, data, token)
    if len(candidates) >= MAX_GUESTS_PER_NAME:
        raise GuestNameLimitError()
    return await _create_guest(data)


# ============ Kratos 훅 판정 ============

async def login_allowed(identity_id: str, schema_id: str | None) -> bool:
    """게스트 로그인 허용 여부. 게스트 행이 있고 접근 정책이 허용해야 한다.

    회원 로그인은 Kratos의 require_verified_address가 정하므로 게스트가 아니면 허용한다.
    """
    if not is_guest_schema(schema_id):
        return True
    guest = _get_guest(identity_id)
    if guest is None:
        return False
    return await check_access(guest)


def _valid_name(name: object) -> bool:
    """이름 규칙에 맞고 이미 NFC이며 앞뒤 공백이 없을 때 True (훅은 Kratos가 저장할 값을 바꿀 수 없다)"""
    if not isinstance(name, str):
        return False
    try:
        return normalize_guest_name(name) == name
    except ValueError:
        return False


async def settings_change_allowed(method: str, identity_id: str, schema_id: str | None, traits: dict) -> bool:
    """설정 변경 허용 여부. 게스트는 로그인 식별자(handle)를 그대로 둔 이름 변경만 된다"""
    if not is_guest_schema(schema_id):
        return True
    if method != "profile":
        return False
    guest = _get_guest(identity_id)
    if guest is None or not await check_access(guest):
        return False
    current = await kratos_admin.get_identity(identity_id)
    if current is None:
        return False
    current_traits = current.get("traits") or {}
    if traits.get("handle") != current_traits.get("handle") or not _valid_name(traits.get("name")):
        return False
    if traits["name"] != current_traits.get("name"):
        with _transaction() as session:
            collect_event(session, GuestRenamed(
                owner_id=guest.identity_id,
                origin=EventOrigin.GUEST,
                guest_id=guest.id,
                resource_type=guest.resource_type,
                resource_id=guest.resource_id,
                name=traits["name"],
            ))
            flush_and_dispatch_events(session)
    return True
