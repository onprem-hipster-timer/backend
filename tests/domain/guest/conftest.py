"""게스트 테스트 fixture

- guest_db: 앱 세션 매니저를 테스트 엔진으로 바꾼다 (게스트 서비스는 자기 세션을 연다)
- kratos: 가짜 Kratos admin·공개 API(/auth 프록시가 넘기는 곳)와 GUEST_ENABLED=true 설정
- host: MEETING 리소스 종류에 등록한 가짜 호스트
- guest_events: 발행된 게스트 이벤트 기록
"""
import httpx
import pytest
from sqlmodel import SQLModel

import app.core.config as app_config
from app.api import auth_proxy
from app.core import kratos_admin
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
        auth_proxy,
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


# ============ 토큰 검증을 켠 앱 ============

ISSUER = "http://localhost:2614/auth/"
AUDIENCE = "http://localhost:2614"


class Tokens:
    """Kratos tokenizer 모양의 ES256 JWT를 만든다"""

    def __init__(self):
        import json

        from joserfc.jwk import ECKey

        self.key = ECKey.generate_key("P-256", parameters={"kid": "guest-test", "use": "sig"}, private=True)
        self.jwks = json.dumps({"keys": [self.key.as_dict(private=False)]})

    def make(self, sub: str, schema_id: str | None, **claims) -> str:
        import time

        from joserfc import jwt

        now = int(time.time())
        body = {"iss": ISSUER, "aud": AUDIENCE, "sub": sub, "iat": now, "nbf": now, "exp": now + 600, **claims}
        if schema_id is not None:
            body["schema_id"] = schema_id
        return jwt.encode({"alg": "ES256", "kid": "guest-test"}, body, self.key, algorithms=["ES256"])

    def guest(self, identity_id: str) -> dict:
        return {"Authorization": f"Bearer {self.make(identity_id, 'guest', name='게스트')}"}

    def member(self, sub: str = "member-1") -> dict:
        token = self.make(sub, "default", email=f"{sub}@example.com", email_verified=True)
        return {"Authorization": f"Bearer {token}"}


def _settings_objects() -> list:
    """모듈마다 import 때 묶어 둔 settings까지 (테스트가 app.core.config.settings를 바꿔 끼웠을 수 있다)"""
    import app.api.auth_proxy
    import app.api.v1.graphql
    import app.core.auth.client
    import app.core.auth.dependencies
    import app.core.auth.middleware
    import app.websocket.auth

    objects = {}
    for obj in (
            app_config.settings,
            app.core.auth.client.settings,
            app.core.auth.dependencies.settings,
            app.core.auth.middleware.settings,
            app.api.v1.graphql.settings,
            app.websocket.auth.settings,
            app.api.auth_proxy.settings,
    ):
        objects[id(obj)] = obj
    return list(objects.values())


@pytest.fixture
def tokens():
    return Tokens()


@pytest.fixture
def guest_client(monkeypatch, guest_db, kratos, host, tokens):
    """OIDC 토큰 검증과 GUEST_ENABLED를 켠 TestClient"""
    from fastapi.testclient import TestClient

    from app.core.auth import oidc_client
    from app.main import app

    for obj in _settings_objects():
        monkeypatch.setattr(obj, "OIDC_ENABLED", True)
        monkeypatch.setattr(obj, "OIDC_ISSUER_URL", ISSUER)
        monkeypatch.setattr(obj, "OIDC_AUDIENCE", AUDIENCE)
        monkeypatch.setattr(obj, "OIDC_JWKS", tokens.jwks)
        monkeypatch.setattr(obj, "GUEST_ENABLED", True)
        monkeypatch.setattr(obj, "KRATOS_ADMIN_URL", KRATOS_ADMIN)
        monkeypatch.setattr(obj, "KRATOS_PUBLIC_URL", KRATOS_PUBLIC)
        monkeypatch.setattr(obj, "KRATOS_HOOK_API_KEY", HOOK_KEY)
        monkeypatch.setattr(obj, "RATE_LIMIT_ENABLED", False)
    oidc_client._jwks_cache.clear()
    yield TestClient(app)
    oidc_client._jwks_cache.clear()


@pytest.fixture
def guest_off(monkeypatch):
    """guest_client를 쓴 채로 GUEST_ENABLED만 끈다"""
    def turn_off():
        for obj in _settings_objects():
            monkeypatch.setattr(obj, "GUEST_ENABLED", False)
    return turn_off
