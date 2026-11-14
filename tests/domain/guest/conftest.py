"""게스트 테스트 fixture

- guest_db: 앱 세션 매니저를 테스트 엔진으로 바꾼다 (게스트 서비스는 자기 세션을 연다)
- kratos: 가짜 Kratos admin·공개 API와 GUEST_ENABLED=true 설정
- host: MEETING 리소스 종류에 등록한 가짜 호스트
- guest_events: 발행된 게스트 이벤트 기록
"""
import httpx
import pytest
from sqlmodel import SQLModel

import app.core.config as app_config
from app.core import kratos_admin, kratos_public
from app.domain.guest.events import GuestDiscarded, GuestRenamed
from app.domain.guest.host import register_guest_host, unregister_guest_host
from app.models.visibility import ResourceType
from app.shared import messagebus
from tests.domain.guest.fakes import KRATOS_ADMIN, KRATOS_PUBLIC, FakeHost, FakeKratos

HOOK_KEY = "test-hook-key"


@pytest.fixture
def guest_db():
    from app.db.session import _session_manager
    from tests.conftest import _create_test_engine

    engine = _create_test_engine()
    original = _session_manager.engine
    _session_manager.engine = engine
    SQLModel.metadata.create_all(engine)
    try:
        yield engine
    finally:
        _session_manager.engine = original
        SQLModel.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def kratos(monkeypatch):
    fake = FakeKratos()
    monkeypatch.setattr(app_config.settings, "GUEST_ENABLED", True)
    monkeypatch.setattr(app_config.settings, "KRATOS_ADMIN_URL", KRATOS_ADMIN)
    monkeypatch.setattr(app_config.settings, "KRATOS_PUBLIC_URL", KRATOS_PUBLIC)
    monkeypatch.setattr(app_config.settings, "KRATOS_HOOK_API_KEY", HOOK_KEY)
    monkeypatch.setattr(
        kratos_admin,
        "_make_client",
        lambda: httpx.AsyncClient(base_url=KRATOS_ADMIN, transport=httpx.MockTransport(fake.admin)),
    )
    monkeypatch.setattr(
        kratos_public,
        "_make_client",
        lambda: httpx.AsyncClient(base_url=KRATOS_PUBLIC, transport=httpx.MockTransport(fake.public)),
    )
    return fake


@pytest.fixture
def host():
    fake = FakeHost()
    register_guest_host(ResourceType.MEETING, fake)
    yield fake
    unregister_guest_host(ResourceType.MEETING)


@pytest.fixture
def guest_events():
    recorded: list = []

    def record(event, session):
        recorded.append(event)

    for event_type in (GuestDiscarded, GuestRenamed):
        messagebus._add_handler(event_type, record)
    yield recorded
    for event_type in (GuestDiscarded, GuestRenamed):
        messagebus.HANDLERS[event_type].remove(record)
