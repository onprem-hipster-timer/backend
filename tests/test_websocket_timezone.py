"""
WebSocket Timer Timezone 테스트

WebSocket에서 timezone 파라미터를 통한 타임존 변환 테스트
"""
import os
import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine

# 테스트 환경 설정
os.environ["OIDC_ENABLED"] = "false"
os.environ["RATE_LIMIT_ENABLED"] = "false"


class TestWebSocketTimezone:
    """WebSocket 타임존 변환 테스트"""

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

    def test_websocket_without_timezone(self, ws_client):
        """timezone 파라미터 없이 연결 시 UTC naive로 반환"""
        with ws_client.websocket_connect("/v1/ws/timers") as websocket:
            # 연결 메시지
            connected = websocket.receive_json()
            assert connected["type"] == "connected"
            
            # 자동 동기화
            sync = websocket.receive_json()
            assert sync["type"] == "timer.sync_result"

            # 타이머 생성
            websocket.send_json({
                "type": "timer.create",
                "payload": {"title": "UTC 테스트", "allocated_duration": 1800},
            })
            create_resp = websocket.receive_json()
            
            assert create_resp["type"] == "timer.created"
            timer = create_resp["payload"]["timer"]
            
            # datetime 필드가 존재하고 문자열 형식인지 확인
            assert "started_at" in timer
            assert isinstance(timer["started_at"], str)
            
            # ISO 8601 형식으로 파싱 가능한지 확인
            started_dt = datetime.fromisoformat(timer["started_at"].replace("Z", "+00:00"))
            assert started_dt is not None

    def test_websocket_with_timezone_asia_seoul(self, ws_client):
        """timezone=Asia/Seoul로 연결 시 KST로 변환"""
        with ws_client.websocket_connect("/v1/ws/timers?timezone=Asia/Seoul") as websocket:
            websocket.receive_json()  # connected
            websocket.receive_json()  # auto sync

            # 타이머 생성
            websocket.send_json({
                "type": "timer.create",
                "payload": {"title": "KST 테스트", "allocated_duration": 1800},
            })
            create_resp = websocket.receive_json()
            
            assert create_resp["type"] == "timer.created"
            timer = create_resp["payload"]["timer"]
            
            # datetime 필드 확인
            started_at_str = timer["started_at"]
            started_dt = datetime.fromisoformat(started_at_str.replace("Z", "+00:00"))
            
            # UTC+09:00 타임존이 적용되었는지 확인
            assert started_dt.tzinfo is not None
            # KST는 UTC+9 (32400초)
            assert started_dt.utcoffset().total_seconds() == 32400

    def test_websocket_with_timezone_utc_offset(self, ws_client):
        """timezone=+09:00로 연결 시 UTC+9로 변환"""
        with ws_client.websocket_connect("/v1/ws/timers?timezone=%2B09:00") as websocket:
            websocket.receive_json()  # connected
            websocket.receive_json()  # auto sync

            # 타이머 생성
            websocket.send_json({
                "type": "timer.create",
                "payload": {"title": "UTC+9 테스트", "allocated_duration": 1800},
            })
            create_resp = websocket.receive_json()
            
            timer = create_resp["payload"]["timer"]
            started_at_str = timer["started_at"]
            started_dt = datetime.fromisoformat(started_at_str.replace("Z", "+00:00"))
            
            # UTC+9 확인
            assert started_dt.utcoffset().total_seconds() == 32400

    def test_websocket_timezone_in_pause_history(self, ws_client):
        """pause_history의 타임스탬프도 타임존 변환 적용"""
        with ws_client.websocket_connect("/v1/ws/timers?timezone=Asia/Seoul") as websocket:
            websocket.receive_json()  # connected
            websocket.receive_json()  # auto sync

            # 타이머 생성
            websocket.send_json({
                "type": "timer.create",
                "payload": {"title": "히스토리 타임존 테스트", "allocated_duration": 1800},
            })
            create_resp = websocket.receive_json()
            timer_id = create_resp["payload"]["timer"]["id"]
            
            # pause_history 확인
            pause_history = create_resp["payload"]["timer"]["pause_history"]
            assert len(pause_history) == 1
            assert pause_history[0]["action"] == "start"
            
            # pause_history의 타임스탬프도 KST로 변환되었는지 확인
            start_at_str = pause_history[0]["at"]
            start_dt = datetime.fromisoformat(start_at_str.replace("Z", "+00:00"))
            assert start_dt.tzinfo is not None
            assert start_dt.utcoffset().total_seconds() == 32400

            # 일시정지
            websocket.send_json({
                "type": "timer.pause",
                "payload": {"timer_id": timer_id},
            })
            pause_resp = websocket.receive_json()
            
            pause_history = pause_resp["payload"]["timer"]["pause_history"]
            assert len(pause_history) == 2
            
            # 모든 타임스탬프가 KST인지 확인
            for event in pause_history:
                event_dt = datetime.fromisoformat(event["at"].replace("Z", "+00:00"))
                assert event_dt.utcoffset().total_seconds() == 32400

    def test_websocket_timezone_in_sync_result(self, ws_client):
        """timer.sync_result 메시지도 타임존 변환 적용"""
        # 먼저 타이머 생성 (timezone 없이)
        with ws_client.websocket_connect("/v1/ws/timers") as ws1:
            ws1.receive_json()  # connected
            ws1.receive_json()  # auto sync
            
            ws1.send_json({
                "type": "timer.create",
                "payload": {"title": "동기화 타임존 테스트", "allocated_duration": 1800},
            })
            ws1.receive_json()  # create response

        # timezone=Asia/Seoul로 새 연결
        with ws_client.websocket_connect("/v1/ws/timers?timezone=Asia/Seoul") as ws2:
            ws2.receive_json()  # connected
            
            # 자동 동기화 메시지 확인
            sync_resp = ws2.receive_json()
            assert sync_resp["type"] == "timer.sync_result"
            assert sync_resp["payload"]["count"] == 1
            
            timer = sync_resp["payload"]["timers"][0]
            started_at_str = timer["started_at"]
            started_dt = datetime.fromisoformat(started_at_str.replace("Z", "+00:00"))
            
            # KST로 변환되었는지 확인
            assert started_dt.utcoffset().total_seconds() == 32400

    def test_websocket_invalid_timezone_fallback_to_utc(self, ws_client):
        """잘못된 timezone 파라미터는 무시하고 UTC 사용"""
        with ws_client.websocket_connect("/v1/ws/timers?timezone=InvalidTimezone") as websocket:
            # 연결은 성공해야 함 (잘못된 timezone은 무시)
            connected = websocket.receive_json()
            assert connected["type"] == "connected"
            
            sync = websocket.receive_json()
            assert sync["type"] == "timer.sync_result"

            # 타이머 생성
            websocket.send_json({
                "type": "timer.create",
                "payload": {"title": "Fallback 테스트", "allocated_duration": 1800},
            })
            create_resp = websocket.receive_json()
            
            # 응답이 정상적으로 오는지 확인
            assert create_resp["type"] == "timer.created"
