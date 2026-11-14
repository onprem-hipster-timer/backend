"""
게스트 서비스

- 접근 정책(check_access): 모든 게스트 확인이 이 함수를 쓴다.
  OPEN이면 허용, CLOSED면 거부하고 게스트를 남긴다, EXPIRED·MISSING이면 거부하고 게스트를 폐기한다
- 폐기(discard_guest, discard_resource_guests): 게스트 행 삭제와 GuestDiscarded 이벤트를 커밋한 뒤
  Kratos identity를 지운다. identity 삭제가 실패해도 행이 없으므로 접근은 닫힌다
  (로그인 훅은 행이 없는 게스트 identity를 거부한다). 실패는 로그로 남긴다
- 이름 찾기(lookup)와 생성(create). 게스트 이름(정규형)은 guest.name에 두고, 리소스 안에서 겹치지 않는 것은
  UNIQUE (resource_type, resource_id, name)이 보장한다. 로그인 식별자(handle)는 "<게스트 행 id>@guest.invalid"
- Kratos 로그인 훅·설정 훅 판정(login_allowed, settings_change_allowed). 회원 로그인은 판정하지 않는다.
  이름 변경은 설정 훅이 guest.name을 바꾼다. 훅이 허용한 뒤 Kratos가 이름 저장에 실패하면 다음 이름 변경까지
  guest.name(찾기·중복 기준)과 Kratos trait name(토큰의 name)이 다르다

DB는 요청 세션이 아니라 자기 세션으로 쓰고 바로 커밋한다. 거부 응답과 함께 폐기가 rollback되지 않게 한다.
DB 작업은 동기 함수로 두고 스레드풀에서 부른다(run_in_threadpool). 풀이 비어 연결을 기다려도 이벤트 루프는 막히지 않는다.
Kratos 호출 동안 트랜잭션을 열어 두지 않는다.

테스트: tests/domain/guest/
"""
import logging
from contextlib import contextmanager
from typing import Iterator
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session
from starlette.concurrency import run_in_threadpool

import app.core.config as app_config
from app.core import kratos_admin
from app.crud import guest as crud
from app.db.session import _session_manager
from app.domain.guest.events import GuestDiscarded, GuestRenamed
from app.domain.guest.exceptions import (
    GuestAccessDeniedError,
    GuestEntryRefusedError,
    GuestNameTakenError,
    GuestServiceUnavailableError,
)
from app.domain.guest.host import GuestHostStatus, host_status
from app.domain.guest.model import Guest
from app.domain.guest.schema.dto import (
    GuestCreate,
    GuestLookup,
    GuestLookupRead,
    GuestRead,
    normalize_guest_name,
)
from app.models.visibility import ResourceType
from app.shared.events import EventOrigin
from app.shared.uow import clear_events, collect_event, flush_and_dispatch_events

logger = logging.getLogger(__name__)

# 게스트 로그인 식별자(handle) "<게스트 행 id>@<이 도메인>"의 도메인. 예약된 TLD라 메일이 가지 않는다.
# handle은 Kratos require_verified_address를 통과하도록 인증된 주소로 만들고, 게스트에게 보여 주지 않는다
GUEST_HANDLE_DOMAIN = "guest.invalid"


def guest_handle(guest_id: UUID) -> str:
    return f"{guest_id}@{GUEST_HANDLE_DOMAIN}"


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


def _read_status(resource_type: ResourceType, resource_id: UUID) -> GuestHostStatus:
    with _session_manager.get_session() as session:
        return host_status(session, resource_type, resource_id)


def _read_guest(identity_id: str) -> Guest | None:
    with _session_manager.get_session() as session:
        return crud.get_guest_by_identity(session, identity_id)


def _read_named_guest(resource_type: ResourceType, resource_id: UUID, name: str) -> Guest | None:
    with _session_manager.get_session() as session:
        return crud.get_guest_by_name(session, resource_type, resource_id, name)


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
    status = await run_in_threadpool(_read_status, guest.resource_type, guest.resource_id)
    if status == GuestHostStatus.OPEN:
        return True
    if status in (GuestHostStatus.EXPIRED, GuestHostStatus.MISSING):
        await discard_guest(guest.identity_id)
    return False


def _delete_guest_row(identity_id: str) -> bool:
    with _transaction() as session:
        guest = crud.get_guest_by_identity(session, identity_id)
        if guest is not None:
            _delete_with_event(session, guest)
    return guest is not None


async def discard_guest(identity_id: str) -> bool:
    """게스트를 폐기한다. 게스트 행이 있었으면 True. Kratos identity는 행이 없어도 지운다"""
    deleted = await run_in_threadpool(_delete_guest_row, identity_id)
    await _delete_identity(identity_id)
    return deleted


def _delete_resource_guest_rows(resource_type: ResourceType, resource_id: UUID) -> list[str]:
    with _transaction() as session:
        guests = crud.list_resource_guests(session, resource_type, resource_id)
        identity_ids = [guest.identity_id for guest in guests]
        for guest in guests:
            _delete_with_event(session, guest)
    return identity_ids


async def discard_resource_guests(resource_type: ResourceType, resource_id: UUID) -> int:
    """리소스의 게스트를 모두 폐기하고 그 수를 돌려준다. 리소스를 지운 뒤(커밋 뒤) 부른다"""
    identity_ids = await run_in_threadpool(_delete_resource_guest_rows, resource_type, resource_id)
    for identity_id in identity_ids:
        await _delete_identity(identity_id)
    return len(identity_ids)


async def authorize(identity_id: str, resource_type: ResourceType, resource_id: UUID) -> Guest:
    """게스트 identity가 이 리소스에 접근할 수 있으면 게스트 행, 아니면 GuestAccessDeniedError"""
    guest = await run_in_threadpool(_read_guest, identity_id)
    if guest is None or guest.resource_type != resource_type or guest.resource_id != resource_id:
        raise GuestAccessDeniedError()
    if not await check_access(guest):
        raise GuestAccessDeniedError()
    return guest


# ============ 이름 찾기와 생성 ============

async def _require_open(resource_type: ResourceType, resource_id: UUID) -> None:
    """리소스가 게스트를 받지 않으면 GuestEntryRefusedError. EXPIRED·MISSING이면 게스트를 모두 폐기한다"""
    status = await run_in_threadpool(_read_status, resource_type, resource_id)
    if status != GuestHostStatus.OPEN:
        if status in (GuestHostStatus.EXPIRED, GuestHostStatus.MISSING):
            await discard_resource_guests(resource_type, resource_id)
        raise GuestEntryRefusedError()


async def lookup(data: GuestLookup) -> GuestLookupRead:
    """리소스에서 이름이 data.name인 게스트의 로그인 식별자(handle). 없으면 handle이 None"""
    await _require_open(data.resource_type, data.resource_id)
    guest = await run_in_threadpool(_read_named_guest, data.resource_type, data.resource_id, data.name)
    return GuestLookupRead(handle=guest_handle(guest.id) if guest is not None else None)


def _insert_guest(guest: Guest) -> None:
    """게스트 행을 넣고 커밋한다. 리소스에 같은 이름이 이미 있으면 IntegrityError"""
    with _session_manager.get_session() as session:
        crud.create_guest(session, guest)
        session.commit()


async def create(data: GuestCreate) -> GuestRead:
    """새 게스트를 만들고 로그인 식별자(handle)를 돌려준다.

    리소스 확인 → 같은 이름 확인(있으면 GuestNameTakenError) → Kratos identity 생성 → 게스트 행 커밋. 행을 넣다가 같은 이름과 겹치면 만든 identity를 지우고 GuestNameTakenError.
    """
    await _require_open(data.resource_type, data.resource_id)
    if await run_in_threadpool(_read_named_guest, data.resource_type, data.resource_id, data.name) is not None:
        raise GuestNameTakenError()

    guest_id = uuid4()
    handle = guest_handle(guest_id)
    identity = await kratos_admin.create_identity(
        app_config.settings.KRATOS_GUEST_SCHEMA_ID,
        {"handle": handle, "name": data.name},
        data.password,
        verified_addresses=(handle,),
    )
    if identity is None:
        raise GuestServiceUnavailableError()
    guest = Guest.model_validate(data, update={"id": guest_id, "identity_id": identity["id"]})
    try:
        await run_in_threadpool(_insert_guest, guest)
    except IntegrityError:
        await _delete_identity(identity["id"])
        raise GuestNameTakenError()
    except BaseException:
        await _delete_identity(identity["id"])
        raise
    return GuestRead(
        guest_id=guest_id,
        handle=handle,
        resource_type=data.resource_type,
        resource_id=data.resource_id,
    )


def _name_taken_by_other(identity_id: str, name: object) -> bool:
    with _session_manager.get_session() as session:
        guest = crud.get_guest_by_identity(session, identity_id)
        if guest is None or not isinstance(name, str):
            return False
        try:
            name = normalize_guest_name(name)
        except ValueError:
            return False
        holder = crud.get_guest_by_name(session, guest.resource_type, guest.resource_id, name)
        return holder is not None and holder.id != guest.id


async def name_taken_by_other(identity_id: str, name: object) -> bool:
    """identity의 게스트 리소스에서 다른 게스트가 이미 name(정규형으로 비교)을 쓰는지 (/auth 프록시의 이름 변경).

    게스트 행이 없거나 이름이 문자열이 아니거나 정규형을 만들 수 없으면 False (설정 훅이 판정한다).
    """
    return await run_in_threadpool(_name_taken_by_other, identity_id, name)


# ============ Kratos 훅 판정 ============

async def login_allowed(identity_id: str, schema_id: str | None) -> bool:
    """게스트 로그인 허용 여부. 게스트 행이 있고 접근 정책이 허용해야 한다.

    회원 로그인은 Kratos의 require_verified_address가 정하므로 게스트가 아니면 허용한다.
    """
    if not is_guest_schema(schema_id):
        return True
    guest = await run_in_threadpool(_read_guest, identity_id)
    if guest is None:
        return False
    return await check_access(guest)


def _valid_name(name: object) -> bool:
    """이름 규칙에 맞고 이미 정규형일 때 True (훅은 Kratos가 저장할 값을 바꿀 수 없다)"""
    if not isinstance(name, str):
        return False
    try:
        return normalize_guest_name(name) == name
    except ValueError:
        return False


def _rename_guest(guest_id: UUID, name: str) -> bool:
    """guest.name을 바꾸고 GuestRenamed를 발행해 커밋한다. 리소스의 다른 게스트가 그 이름이면 False"""
    try:
        with _transaction() as session:
            guest = session.get(Guest, guest_id)
            if guest is None:
                return False
            guest.name = name
            session.add(guest)
            session.flush()
            collect_event(session, GuestRenamed(
                owner_id=guest.identity_id,
                origin=EventOrigin.GUEST,
                guest_id=guest.id,
                resource_type=guest.resource_type,
                resource_id=guest.resource_id,
                name=name,
            ))
            flush_and_dispatch_events(session)
    except IntegrityError:
        return False
    return True


async def settings_change_allowed(method: str, identity_id: str, schema_id: str | None, traits: dict) -> bool:
    """설정 변경 허용 여부. 게스트는 로그인 식별자(handle)를 그대로 둔 이름 변경만 되고,
    같은 리소스의 다른 게스트가 쓰는 이름으로는 바꿀 수 없다. Kratos를 부르지 않는다"""
    if not is_guest_schema(schema_id):
        return True
    if method != "profile":
        return False
    guest = await run_in_threadpool(_read_guest, identity_id)
    if guest is None or not await check_access(guest):
        return False
    if traits.get("handle") != guest_handle(guest.id) or not _valid_name(traits.get("name")):
        return False
    if traits["name"] != guest.name:
        return await run_in_threadpool(_rename_guest, guest.id, traits["name"])
    return True
