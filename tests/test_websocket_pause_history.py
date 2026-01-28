"""
WebSocket Timer pause_history 상세 테스트

타이머의 pause_history 필드에 대한 상세 검증
"""
import os
import pytest
from datetime import datetime
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine

# 테스트 환경 설정
os.environ["OIDC_ENABLED"] = "false"
os.environ["RATE_LIMIT_ENABLED"] = "false"


class TestWebSocketPauseHistory:
    """pause_history 필드 상세 검증 테스트"""

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

    def test_pause_history_on_create(self, ws_client):
        """타이머 생성 시 pause_history 초기 구조 검증"""
        with ws_client.websocket_connect("/v1/ws/timers") as websocket:
            websocket.receive_json()  # connected
            websocket.receive_json()  # auto sync

            # 타이머 생성
            websocket.send_json({
                "type": "timer.create",
                "payload": {"title": "히스토리 테스트", "allocated_duration": 1800},
            })
            create_resp = websocket.receive_json()
            
            assert create_resp["type"] == "timer.created"
            timer = create_resp["payload"]["timer"]
            
            # pause_history 검증
            assert "pause_history" in timer
            assert len(timer["pause_history"]) == 1
            assert timer["pause_history"][0]["action"] == "start"
            assert "at" in timer["pause_history"][0]

    def test_pause_history_full_lifecycle(self, ws_client):
        """전체 라이프사이클 pause_history 추적"""
        with ws_client.websocket_connect("/v1/ws/timers") as websocket:
            websocket.receive_json()  # connected
            websocket.receive_json()  # auto sync

            # 1. 생성 (start)
            websocket.send_json({
                "type": "timer.create",
                "payload": {"title": "라이프사이클 테스트", "allocated_duration": 1800},
            })
            create_resp = websocket.receive_json()
            timer_id = create_resp["payload"]["timer"]["id"]
            assert len(create_resp["payload"]["timer"]["pause_history"]) == 1
            assert create_resp["payload"]["timer"]["pause_history"][0]["action"] == "start"

            # 2. 일시정지 (pause)
            websocket.send_json({
                "type": "timer.pause",
                "payload": {"timer_id": timer_id},
            })
            pause_resp = websocket.receive_json()
            assert len(pause_resp["payload"]["timer"]["pause_history"]) == 2
            assert pause_resp["payload"]["timer"]["pause_history"][1]["action"] == "pause"

            # 3. 재개 (resume)
            websocket.send_json({
                "type": "timer.resume",
                "payload": {"timer_id": timer_id},
            })
            resume_resp = websocket.receive_json()
            assert len(resume_resp["payload"]["timer"]["pause_history"]) == 3
            assert resume_resp["payload"]["timer"]["pause_history"][2]["action"] == "resume"

            # 4. 다시 일시정지
            websocket.send_json({
                "type": "timer.pause",
                "payload": {"timer_id": timer_id},
            })
            pause2_resp = websocket.receive_json()
            assert len(pause2_resp["payload"]["timer"]["pause_history"]) == 4
            assert pause2_resp["payload"]["timer"]["pause_history"][3]["action"] == "pause"

            # 5. 다시 재개
            websocket.send_json({
                "type": "timer.resume",
                "payload": {"timer_id": timer_id},
            })
            resume2_resp = websocket.receive_json()
            assert len(resume2_resp["payload"]["timer"]["pause_history"]) == 5
            assert resume2_resp["payload"]["timer"]["pause_history"][4]["action"] == "resume"

            # 6. 종료 (stop)
            websocket.send_json({
                "type": "timer.stop",
                "payload": {"timer_id": timer_id},
            })
            stop_resp = websocket.receive_json()
            assert len(stop_resp["payload"]["timer"]["pause_history"]) == 6
            assert stop_resp["payload"]["timer"]["pause_history"][5]["action"] == "stop"
            
            # 전체 히스토리 순서 검증
            expected_actions = ["start", "pause", "resume", "pause", "resume", "stop"]
            actual_actions = [h["action"] for h in stop_resp["payload"]["timer"]["pause_history"]]
            assert actual_actions == expected_actions

    def test_pause_history_timestamps_valid(self, ws_client):
        """pause_history 타임스탬프 유효성 및 순서 검증"""
        with ws_client.websocket_connect("/v1/ws/timers") as websocket:
            websocket.receive_json()  # connected
            websocket.receive_json()  # auto sync

            # 타이머 생성
            websocket.send_json({
                "type": "timer.create",
                "payload": {"title": "타임스탬프 테스트", "allocated_duration": 1800},
            })
            create_resp = websocket.receive_json()
            timer_id = create_resp["payload"]["timer"]["id"]

            # 일시정지
            websocket.send_json({
                "type": "timer.pause",
                "payload": {"timer_id": timer_id},
            })
            pause_resp = websocket.receive_json()
            
            history = pause_resp["payload"]["timer"]["pause_history"]
            
            # 각 타임스탬프가 유효한 ISO 8601 형식인지 확인
            for entry in history:
                assert "at" in entry
                # ISO 8601 파싱 시도
                try:
                    datetime.fromisoformat(entry["at"].replace("Z", "+00:00"))
                except ValueError:
                    pytest.fail(f"Invalid timestamp format: {entry['at']}")
            
            # 시간 순서 검증 (이전 < 다음)
            for i in range(len(history) - 1):
                t1 = datetime.fromisoformat(history[i]["at"].replace("Z", "+00:00"))
                t2 = datetime.fromisoformat(history[i+1]["at"].replace("Z", "+00:00"))
                assert t1 <= t2, f"Timestamps out of order: {history[i]['at']} > {history[i+1]['at']}"
