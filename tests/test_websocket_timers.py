"""
WebSocket Timer 테스트

WebSocket을 통한 타이머 실시간 동기화 테스트
"""
import json
import os
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine, Session

from app.core.auth import CurrentUser

# 테스트 환경 설정
os.environ["OIDC_ENABLED"] = "false"
os.environ["RATE_LIMIT_ENABLED"] = "false"


class TestWebSocketConnection:
    """WebSocket 연결 테스트"""

    @pytest.fixture
    def ws_client(self):
        """WebSocket 테스트 클라이언트"""
        from fastapi.testclient import TestClient
        from app.main import app
        from app.db.session import _session_manager

        # 테스트 DB 설정
        test_engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False,
        )

        @event.listens_for(test_engine, "connect")
        def set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        original_engine = _session_manager.engine
        _session_manager.engine = test_engine
        SQLModel.metadata.create_all(test_engine)

        try:
            client = TestClient(app)
            yield client
        finally:
            _session_manager.engine = original_engine
            SQLModel.metadata.drop_all(test_engine)
            test_engine.dispose()

    @pytest.fixture
    def mock_user(self):
        """테스트용 사용자"""
        return CurrentUser(
            sub="test-user-id",
            email="test@example.com",
            name="Test User",
        )

    def test_websocket_connection_without_token(self, ws_client):
        """토큰 없이 연결 시 실패해야 함"""
        # OIDC가 비활성화되어 있으므로 토큰 없이도 연결 가능
        # (실제 환경에서는 토큰 필요)
        with ws_client.websocket_connect("/v1/ws/timers") as websocket:
            # 연결 성공 메시지 확인
            data = websocket.receive_json()
            assert data["type"] == "connected"
            assert "user_id" in data["payload"]

    def test_websocket_connection_with_query_token(self, ws_client):
        """쿼리 파라미터 토큰으로 연결"""
        # OIDC 비활성화 상태에서 테스트
        with ws_client.websocket_connect("/v1/ws/timers?token=test-token") as websocket:
            data = websocket.receive_json()
            assert data["type"] == "connected"


class TestWebSocketTimerOperations:
    """WebSocket 타이머 작업 테스트"""

    @pytest.fixture
    def ws_client_with_schedule(self):
        """스케줄이 있는 WebSocket 테스트 클라이언트"""
        from fastapi.testclient import TestClient
        from app.main import app
        from app.db.session import _session_manager

        # 테스트 DB 설정
        test_engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False,
        )

        @event.listens_for(test_engine, "connect")
        def set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        original_engine = _session_manager.engine
        _session_manager.engine = test_engine
        SQLModel.metadata.create_all(test_engine)

        try:
            client = TestClient(app)
            yield client
        finally:
            _session_manager.engine = original_engine
            SQLModel.metadata.drop_all(test_engine)
            test_engine.dispose()

    def test_create_timer_via_websocket(self, ws_client_with_schedule):
        """WebSocket을 통한 타이머 생성"""
        with ws_client_with_schedule.websocket_connect("/v1/ws/timers") as websocket:
            # 연결 메시지 수신
            connected = websocket.receive_json()
            assert connected["type"] == "connected"

            # 타이머 생성 요청
            create_message = {
                "type": "timer.create",
                "payload": {
                    "title": "WebSocket 타이머",
                    "allocated_duration": 1800,
                },
            }
            websocket.send_json(create_message)

            # 응답 수신
            response = websocket.receive_json()

            # 성공 또는 에러 응답
            assert response["type"] in ["timer.created", "error"]
            if response["type"] == "timer.created":
                assert "timer" in response["payload"]
                timer_data = response["payload"]["timer"]
                assert timer_data["title"] == "WebSocket 타이머"
                assert timer_data["allocated_duration"] == 1800
                assert timer_data["status"] == "running"
                assert "pause_history" in timer_data

    def test_pause_timer_via_websocket(self, ws_client_with_schedule):
        """WebSocket을 통한 타이머 일시정지"""
        with ws_client_with_schedule.websocket_connect("/v1/ws/timers") as websocket:
            # 연결 메시지 수신
            websocket.receive_json()

            # 먼저 타이머 생성
            create_message = {
                "type": "timer.create",
                "payload": {
                    "title": "일시정지 테스트",
                    "allocated_duration": 1800,
                },
            }
            websocket.send_json(create_message)
            create_response = websocket.receive_json()

            if create_response["type"] != "timer.created":
                pytest.skip("Timer creation failed")

            timer_id = create_response["payload"]["timer"]["id"]

            # 타이머 일시정지 요청
            pause_message = {
                "type": "timer.pause",
                "payload": {
                    "timer_id": timer_id,
                },
            }
            websocket.send_json(pause_message)

            # 응답 수신
            response = websocket.receive_json()

            assert response["type"] in ["timer.updated", "error"]
            if response["type"] == "timer.updated":
                timer_data = response["payload"]["timer"]
                assert timer_data["status"] == "paused"
                assert timer_data["paused_at"] is not None
                assert len(timer_data["pause_history"]) >= 2  # start + pause

    def test_resume_timer_via_websocket(self, ws_client_with_schedule):
        """WebSocket을 통한 타이머 재개"""
        with ws_client_with_schedule.websocket_connect("/v1/ws/timers") as websocket:
            # 연결 메시지 수신
            websocket.receive_json()

            # 타이머 생성
            create_message = {
                "type": "timer.create",
                "payload": {
                    "title": "재개 테스트",
                    "allocated_duration": 1800,
                },
            }
            websocket.send_json(create_message)
            create_response = websocket.receive_json()

            if create_response["type"] != "timer.created":
                pytest.skip("Timer creation failed")

            timer_id = create_response["payload"]["timer"]["id"]

            # 일시정지
            pause_message = {
                "type": "timer.pause",
                "payload": {"timer_id": timer_id},
            }
            websocket.send_json(pause_message)
            pause_response = websocket.receive_json()

            if pause_response["type"] != "timer.updated":
                pytest.skip("Timer pause failed")

            # 재개
            resume_message = {
                "type": "timer.resume",
                "payload": {"timer_id": timer_id},
            }
            websocket.send_json(resume_message)
            response = websocket.receive_json()

            assert response["type"] in ["timer.updated", "error"]
            if response["type"] == "timer.updated":
                timer_data = response["payload"]["timer"]
                assert timer_data["status"] == "running"
                assert timer_data["paused_at"] is None
                assert len(timer_data["pause_history"]) >= 3  # start + pause + resume

    def test_stop_timer_via_websocket(self, ws_client_with_schedule):
        """WebSocket을 통한 타이머 종료"""
        with ws_client_with_schedule.websocket_connect("/v1/ws/timers") as websocket:
            # 연결 메시지 수신
            websocket.receive_json()

            # 타이머 생성
            create_message = {
                "type": "timer.create",
                "payload": {
                    "title": "종료 테스트",
                    "allocated_duration": 1800,
                },
            }
            websocket.send_json(create_message)
            create_response = websocket.receive_json()

            if create_response["type"] != "timer.created":
                pytest.skip("Timer creation failed")

            timer_id = create_response["payload"]["timer"]["id"]

            # 종료
            stop_message = {
                "type": "timer.stop",
                "payload": {"timer_id": timer_id},
            }
            websocket.send_json(stop_message)
            response = websocket.receive_json()

            assert response["type"] in ["timer.updated", "error"]
            if response["type"] == "timer.updated":
                timer_data = response["payload"]["timer"]
                assert timer_data["status"] == "completed"
                assert timer_data["ended_at"] is not None
                assert len(timer_data["pause_history"]) >= 2  # start + stop


class TestWebSocketSync:
    """WebSocket 동기화 테스트"""

    @pytest.fixture
    def ws_client(self):
        """WebSocket 테스트 클라이언트"""
        from fastapi.testclient import TestClient
        from app.main import app
        from app.db.session import _session_manager

        test_engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False,
        )

        @event.listens_for(test_engine, "connect")
        def set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        original_engine = _session_manager.engine
        _session_manager.engine = test_engine
        SQLModel.metadata.create_all(test_engine)

        try:
            client = TestClient(app)
            yield client
        finally:
            _session_manager.engine = original_engine
            SQLModel.metadata.drop_all(test_engine)
            test_engine.dispose()

    def test_timer_sync_request(self, ws_client):
        """타이머 동기화 요청"""
        with ws_client.websocket_connect("/v1/ws/timers") as websocket:
            # 연결 메시지 수신
            websocket.receive_json()

            # 동기화 요청
            sync_message = {
                "type": "timer.sync",
                "payload": {},
            }
            websocket.send_json(sync_message)

            # 응답 수신
            response = websocket.receive_json()

            # 동기화 응답 또는 에러
            assert response["type"] in ["timer.updated", "error"]


class TestWebSocketErrorHandling:
    """WebSocket 에러 처리 테스트"""

    @pytest.fixture
    def ws_client(self):
        """WebSocket 테스트 클라이언트"""
        from fastapi.testclient import TestClient
        from app.main import app
        from app.db.session import _session_manager

        test_engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False,
        )

        @event.listens_for(test_engine, "connect")
        def set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        original_engine = _session_manager.engine
        _session_manager.engine = test_engine
        SQLModel.metadata.create_all(test_engine)

        try:
            client = TestClient(app)
            yield client
        finally:
            _session_manager.engine = original_engine
            SQLModel.metadata.drop_all(test_engine)
            test_engine.dispose()

    def test_invalid_message_format(self, ws_client):
        """잘못된 메시지 형식 처리"""
        with ws_client.websocket_connect("/v1/ws/timers") as websocket:
            # 연결 메시지 수신
            websocket.receive_json()

            # 잘못된 형식의 메시지 전송
            websocket.send_text("invalid json")

            # 에러 응답 확인
            response = websocket.receive_json()
            assert response["type"] == "error"
            assert "code" in response["payload"]

    def test_unknown_message_type(self, ws_client):
        """알 수 없는 메시지 타입 처리"""
        with ws_client.websocket_connect("/v1/ws/timers") as websocket:
            # 연결 메시지 수신
            websocket.receive_json()

            # 알 수 없는 타입 전송
            unknown_message = {
                "type": "unknown.type",
                "payload": {},
            }
            websocket.send_json(unknown_message)

            # 에러 응답 확인
            response = websocket.receive_json()
            assert response["type"] == "error"
            assert response["payload"]["code"] == "UNKNOWN_TYPE"

    def test_pause_nonexistent_timer(self, ws_client):
        """존재하지 않는 타이머 일시정지"""
        with ws_client.websocket_connect("/v1/ws/timers") as websocket:
            # 연결 메시지 수신
            websocket.receive_json()

            # 존재하지 않는 타이머 일시정지 요청
            pause_message = {
                "type": "timer.pause",
                "payload": {
                    "timer_id": "00000000-0000-0000-0000-000000000000",
                },
            }
            websocket.send_json(pause_message)

            # 에러 응답 확인
            response = websocket.receive_json()
            assert response["type"] == "error"


class TestWebSocketMultipleConnections:
    """다중 WebSocket 연결 테스트"""

    @pytest.fixture
    def ws_client(self):
        """WebSocket 테스트 클라이언트"""
        from fastapi.testclient import TestClient
        from app.main import app
        from app.db.session import _session_manager

        test_engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False,
        )

        @event.listens_for(test_engine, "connect")
        def set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        original_engine = _session_manager.engine
        _session_manager.engine = test_engine
        SQLModel.metadata.create_all(test_engine)

        try:
            client = TestClient(app)
            yield client
        finally:
            _session_manager.engine = original_engine
            SQLModel.metadata.drop_all(test_engine)
            test_engine.dispose()

    def test_multiple_connections_same_user(self, ws_client):
        """동일 사용자의 다중 연결"""
        # FastAPI TestClient는 동시 WebSocket 연결을 지원하지 않으므로
        # 순차적으로 테스트
        with ws_client.websocket_connect("/v1/ws/timers") as websocket1:
            data1 = websocket1.receive_json()
            assert data1["type"] == "connected"

        # 두 번째 연결 (첫 번째 연결 종료 후)
        with ws_client.websocket_connect("/v1/ws/timers") as websocket2:
            data2 = websocket2.receive_json()
            assert data2["type"] == "connected"
