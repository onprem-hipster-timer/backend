"""EXPIRED·MISSING 리소스의 게스트 정리 (discard_stale_guests)

- 게스트가 있는 리소스마다 호스트 상태를 읽어 EXPIRED·MISSING이면 그 리소스의 게스트를 모두 폐기한다
  (게스트 행·약관 동의·Kratos identity 삭제, 게스트마다 GuestDiscarded 한 번). OPEN·CLOSED 리소스의 게스트는 남는다
- 호스트를 등록하지 않은 리소스 종류는 MISSING이다. 리소스는 (resource_type, resource_id)로 가린다
- 한 리소스의 실패(호스트 오류, 폐기 중 DB 오류)는 다른 리소스를 막지 않고, 그 리소스의 게스트는 남는다
- Kratos identity 삭제가 실패해도 행은 지우고 수에 넣는다. 다시 시도하지 않는다
- GUEST_ENABLED가 꺼져 있어도 폐기한다
- 게스트가 없으면 쿼리 하나만 하고 Kratos를 부르지 않는다
"""
import logging
import uuid

import pytest
from sqlalchemy import event

import app.core.config as app_config
from app.db.session import _session_manager
from app.domain.consent import service as consent_service
from app.domain.consent.schema.dto import ConsentCreate
from app.domain.guest import service
from app.domain.guest.events import GuestDiscarded
from app.domain.guest.host import GuestHostStatus, unregister_guest_host
from app.models.visibility import ResourceType
from app.shared.events import EventOrigin
from tests.domain.guest.helpers import consent_body, consent_rows, guest_rows, make_guest

pytestmark = pytest.mark.usefixtures("guest_db")


def _make_guests(kratos, resource_id, count, resource_type=ResourceType.MEETING):
    """리소스에 게스트 count명과 각자의 약관 동의를 만든다"""
    guests = [make_guest(kratos, resource_id, name=f"게스트{i}", resource_type=resource_type) for i in range(count)]
    with _session_manager.get_session() as session:
        for guest in guests:
            consent_service.record_consent(session, guest.identity_id, ConsentCreate(**consent_body()))
        session.commit()
    return guests


def _open_and_closed(kratos, host):
    """OPEN 리소스와 CLOSED 리소스의 게스트"""
    open_resource, closed_resource = uuid.uuid4(), uuid.uuid4()
    host.statuses[open_resource] = GuestHostStatus.OPEN
    host.statuses[closed_resource] = GuestHostStatus.CLOSED
    return _make_guests(kratos, open_resource, 2) + _make_guests(kratos, closed_resource, 1)


def _by_guest(item) -> str:
    return str(item.guest_id)


def _assert_outcome(kratos, guest_events, discarded, kept):
    """discarded는 행·동의·identity가 지워지고 GuestDiscarded를 한 번씩 받았고, kept는 그대로다"""
    assert sorted(g.id for g in guest_rows()) == sorted(g.id for g in kept)
    assert consent_rows() == {(g.identity_id, app_config.settings.CONSENT_VERSION) for g in kept}
    assert sorted(kratos.deleted) == sorted(g.identity_id for g in discarded)
    assert all(g.identity_id in kratos.identities for g in kept)
    expected_events = [
        GuestDiscarded(
            owner_id=g.identity_id,
            origin=EventOrigin.GUEST,
            guest_id=g.id,
            resource_type=g.resource_type,
            resource_id=g.resource_id,
        )
        for g in discarded
    ]
    assert sorted(guest_events, key=_by_guest) == sorted(expected_events, key=_by_guest)


@pytest.mark.parametrize("case", ["expired", "missing", "unregistered_type"])
@pytest.mark.asyncio
async def test_guests_of_expired_or_missing_resource_are_discarded(kratos, host, guest_events, case):
    resource = uuid.uuid4()
    if case == "unregistered_type":
        unregister_guest_host(ResourceType.TODO)
        stale = _make_guests(kratos, resource, 2, ResourceType.TODO)
    else:
        host.statuses[resource] = GuestHostStatus.EXPIRED if case == "expired" else GuestHostStatus.MISSING
        stale = _make_guests(kratos, resource, 2)
    kept = _open_and_closed(kratos, host)

    assert await service.discard_stale_guests() == 2

    _assert_outcome(kratos, guest_events, stale, kept)


@pytest.mark.asyncio
async def test_one_run_covers_resources_of_every_status(kratos, host, guest_events):
    unregister_guest_host(ResourceType.TODO)
    expired_a, expired_b, missing = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    host.statuses[expired_a] = host.statuses[expired_b] = GuestHostStatus.EXPIRED
    host.statuses[missing] = GuestHostStatus.MISSING
    discarded = (
        _make_guests(kratos, expired_a, 3)
        + _make_guests(kratos, expired_b, 1)
        + _make_guests(kratos, missing, 2)
        + _make_guests(kratos, uuid.uuid4(), 1, ResourceType.TODO)
    )
    kept = _open_and_closed(kratos, host)

    assert await service.discard_stale_guests() == 7

    _assert_outcome(kratos, guest_events, discarded, kept)


@pytest.mark.asyncio
async def test_same_id_under_another_type_is_another_resource(kratos, host, guest_events):
    unregister_guest_host(ResourceType.TODO)
    resource = uuid.uuid4()
    host.statuses[resource] = GuestHostStatus.OPEN
    kept = _make_guests(kratos, resource, 1)
    discarded = _make_guests(kratos, resource, 1, ResourceType.TODO)

    assert await service.discard_stale_guests() == 1

    _assert_outcome(kratos, guest_events, discarded, kept)


@pytest.mark.parametrize("failure", ["host_raises", "discard_raises"])
@pytest.mark.asyncio
async def test_failure_on_one_resource_does_not_stop_the_others(
        kratos, host, guest_events, monkeypatch, caplog, failure
):
    """처음 처리하는 리소스가 실패한다. 나머지 리소스는 폐기되고 실패한 리소스의 게스트는 남는다"""
    # alembic 마이그레이션 테스트의 fileConfig가 이미 있던 로거를 끈다
    monkeypatch.setattr(service.logger, "disabled", False)
    resources = [uuid.uuid4() for _ in range(3)]
    guests = {}
    for resource in resources:
        host.statuses[resource] = GuestHostStatus.EXPIRED
        guests[resource] = _make_guests(kratos, resource, 2)
    failed: list = []
    if failure == "host_raises":
        status_of = host.guest_status

        def guest_status(session, resource_id):
            if not failed:
                failed.append(resource_id)
                raise RuntimeError("host failure")
            return status_of(session, resource_id)

        monkeypatch.setattr(host, "guest_status", guest_status)
    else:
        delete_guest = service.crud.delete_guest

        def failing_delete(session, guest):
            if not failed:
                failed.append(guest.resource_id)
                raise RuntimeError("db failure")
            delete_guest(session, guest)

        monkeypatch.setattr(service.crud, "delete_guest", failing_delete)

    with caplog.at_level(logging.ERROR):
        assert await service.discard_stale_guests() == 4

    [failed_resource] = failed
    discarded = [g for resource in resources if resource != failed_resource for g in guests[resource]]
    _assert_outcome(kratos, guest_events, discarded, guests[failed_resource])
    assert str(failed_resource) in caplog.text


@pytest.mark.asyncio
async def test_without_guests_runs_one_query_and_calls_no_kratos(kratos, host, guest_db, monkeypatch):
    admin_requests = []
    admin = kratos.admin

    def recording_admin(request):
        admin_requests.append(request)
        return admin(request)

    monkeypatch.setattr(kratos, "admin", recording_admin)
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(guest_db, "before_cursor_execute", record)
    try:
        assert await service.discard_stale_guests() == 0
    finally:
        event.remove(guest_db, "before_cursor_execute", record)

    assert len(statements) == 1
    assert admin_requests == []


@pytest.mark.asyncio
async def test_second_run_discards_nothing(kratos, host, guest_events):
    resource = uuid.uuid4()
    host.statuses[resource] = GuestHostStatus.EXPIRED
    discarded = _make_guests(kratos, resource, 2)
    kept = _open_and_closed(kratos, host)
    assert await service.discard_stale_guests() == 2

    assert await service.discard_stale_guests() == 0

    _assert_outcome(kratos, guest_events, discarded, kept)


@pytest.mark.asyncio
async def test_discards_while_guests_are_turned_off(kratos, host, guest_events, monkeypatch):
    monkeypatch.setattr(app_config.settings, "GUEST_ENABLED", False)
    resource = uuid.uuid4()
    host.statuses[resource] = GuestHostStatus.EXPIRED
    discarded = _make_guests(kratos, resource, 2)
    kept = _open_and_closed(kratos, host)

    assert await service.discard_stale_guests() == 2

    _assert_outcome(kratos, guest_events, discarded, kept)


@pytest.mark.asyncio
async def test_identity_delete_failure_still_discards_and_counts(kratos, host, guest_events, monkeypatch, caplog):
    monkeypatch.setattr(service.logger, "disabled", False)
    resource = uuid.uuid4()
    host.statuses[resource] = GuestHostStatus.EXPIRED
    discarded = _make_guests(kratos, resource, 2)
    kratos.down.add("admin")

    with caplog.at_level(logging.WARNING):
        assert await service.discard_stale_guests() == 2

    assert guest_rows() == []
    assert consent_rows() == set()
    assert sorted(e.guest_id for e in guest_events) == sorted(g.id for g in discarded)
    assert all(g.identity_id in kratos.identities for g in discarded)
    assert all(g.identity_id in caplog.text for g in discarded)

    kratos.down.clear()
    assert await service.discard_stale_guests() == 0
    assert kratos.deleted == []
