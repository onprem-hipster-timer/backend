"""
OriginVerifyMiddleware 테스트

- 설정 시: 올바른 헤더만 통과, 없거나 틀리면 403 (HTTP, WebSocket, 미지의 경로 포함)
- /health는 헤더 없이 통과 (startup probe)
- ORIGIN_VERIFY_HEADER/SECRET 미설정 시 검사 비활성
"""
import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import app.core.config as config_module
from app.core.config import Settings
from app.middleware.origin_verify import OriginVerifyMiddleware

HEADER = "X-Origin-Verify"
SECRET = "test-origin-secret"


@pytest.fixture
def origin_settings(monkeypatch):
    """ORIGIN_VERIFY 설정을 켠 settings로 교체 (monkeypatch가 원복)"""
    monkeypatch.setattr(
        config_module,
        "settings",
        Settings(ORIGIN_VERIFY_HEADER=HEADER, ORIGIN_VERIFY_SECRET=SECRET),
    )


@pytest.fixture
def no_origin_settings(monkeypatch):
    """ORIGIN_VERIFY 설정이 빈 settings로 교체"""
    monkeypatch.setattr(
        config_module,
        "settings",
        Settings(ORIGIN_VERIFY_HEADER="", ORIGIN_VERIFY_SECRET=""),
    )


@pytest.fixture
def client():
    """미들웨어만 붙인 최소 앱"""
    app = FastAPI()
    app.add_middleware(OriginVerifyMiddleware)

    @app.get("/v1/ping")
    def ping():
        return {"ok": True}

    @app.get("/health")
    def health():
        return {"status": "healthy"}

    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        await websocket.accept()
        await websocket.send_text("hello")
        await websocket.close()

    return TestClient(app)


class TestOriginVerifyEnabled:
    def test_valid_header_passes(self, origin_settings, client):
        response = client.get("/v1/ping", headers={HEADER: SECRET})
        assert response.status_code == 200

    def test_header_name_case_insensitive(self, origin_settings, client):
        response = client.get("/v1/ping", headers={HEADER.lower(): SECRET})
        assert response.status_code == 200

    def test_missing_header_rejected(self, origin_settings, client):
        response = client.get("/v1/ping")
        assert response.status_code == 403
        assert response.text == "Forbidden"

    def test_wrong_header_rejected(self, origin_settings, client):
        response = client.get("/v1/ping", headers={HEADER: "wrong"})
        assert response.status_code == 403

    def test_unknown_path_rejected(self, origin_settings, client):
        """라우트가 없는 경로도 404 전에 403"""
        response = client.get("/no-such-path")
        assert response.status_code == 403

    def test_health_subpath_not_exempt(self, origin_settings, client):
        response = client.get("/health/extra")
        assert response.status_code == 403

    def test_health_exempt(self, origin_settings, client):
        response = client.get("/health")
        assert response.status_code == 200

    def test_websocket_valid_header_passes(self, origin_settings, client):
        with client.websocket_connect("/ws", headers={HEADER: SECRET}) as ws:
            assert ws.receive_text() == "hello"

    def test_websocket_missing_header_rejected(self, origin_settings, client):
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/ws"):
                pass
        assert exc_info.value.code == 1008


class TestOriginVerifyDisabled:
    def test_no_header_passes_when_not_configured(self, no_origin_settings, client):
        response = client.get("/v1/ping")
        assert response.status_code == 200

    def test_websocket_passes_when_not_configured(self, no_origin_settings, client):
        with client.websocket_connect("/ws") as ws:
            assert ws.receive_text() == "hello"

    def test_header_only_without_secret_disabled(self, monkeypatch, client):
        monkeypatch.setattr(
            config_module,
            "settings",
            Settings(ORIGIN_VERIFY_HEADER=HEADER, ORIGIN_VERIFY_SECRET=""),
        )
        response = client.get("/v1/ping")
        assert response.status_code == 200


class TestAppRegistration:
    """실제 앱에 등록됐는지와 /health 예외 확인 (lifespan 미실행)"""

    def test_app_health_without_header(self, origin_settings):
        from app.main import app
        response = TestClient(app).get("/health")
        assert response.status_code == 200

    def test_app_rejects_without_header(self, origin_settings):
        from app.main import app
        response = TestClient(app).get("/v1/tags")
        assert response.status_code == 403
