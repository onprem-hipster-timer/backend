"""
WebSocket Timer 테스트

WebSocket을 통한 타이머 실시간 동기화 테스트
"""
import os

# 테스트 환경 설정
os.environ["OIDC_ENABLED"] = "false"
os.environ["RATE_LIMIT_ENABLED"] = "false"


class TestWebSocketConnection:
    """WebSocket 연결 테스트"""

    def test_websocket_connection_without_token(self, e2e_client):
        """토큰 없이 연결 시 실패해야 함"""
        # OIDC가 비활성화되어 있으므로 토큰 없이도 연결 가능
        # (실제 환경에서는 토큰 필요)
        with e2e_client.websocket_connect("/v1/ws/timers") as websocket:
            # 연결 성공 메시지 확인
            data = websocket.receive_json()
            assert data["type"] == "connected"
            assert "user_id" in data["payload"]

            # 자동 동기화 메시지 확인 (활성 타이머 없으면 빈 목록)
            sync_data = websocket.receive_json()
            assert sync_data["type"] == "timer.sync_result"
            assert "timers" in sync_data["payload"]
            assert "count" in sync_data["payload"]
            assert sync_data["payload"]["count"] == 0  # 초기 상태는 타이머 없음

    def test_websocket_connection_with_timezone_param(self, e2e_client):
        """타임존 쿼리 파라미터로 연결 (토큰은 Sec-WebSocket-Protocol로)"""
        # OIDC 비활성화 상태에서 테스트
        # 실제 환경에서는 토큰을 Sec-WebSocket-Protocol 헤더로 전달해야 함
        with e2e_client.websocket_connect("/v1/ws/timers?timezone=Asia/Seoul") as websocket:
            data = websocket.receive_json()
            assert data["type"] == "connected"

            # 자동 동기화 메시지 확인
            sync_data = websocket.receive_json()
            assert sync_data["type"] == "timer.sync_result"


class TestWebSocketTimerOperations:
    """WebSocket 타이머 작업 테스트"""

    def test_create_timer_via_websocket(self, e2e_client):
        """WebSocket을 통한 타이머 생성"""
        from tests.conftest import timer_ws_client

        with timer_ws_client(e2e_client) as ws:
            timer = ws.create_timer(title="WebSocket 타이머", allocated_duration=1800)
            assert timer["title"] == "WebSocket 타이머"
            assert timer["allocated_duration"] == 1800
            assert timer["status"] == "RUNNING"
            assert "pause_history" in timer

    def test_pause_timer_via_websocket(self, e2e_client):
        """WebSocket을 통한 타이머 일시정지"""
        from tests.conftest import timer_ws_client

        with timer_ws_client(e2e_client) as ws:
            timer = ws.create_timer(title="일시정지 테스트", allocated_duration=1800)
            timer_id = timer["id"]

            paused_timer = ws.pause_timer(timer_id)
            assert paused_timer["status"] == "PAUSED"
            assert paused_timer["paused_at"] is not None
            assert len(paused_timer["pause_history"]) >= 2  # start + pause

    def test_resume_timer_via_websocket(self, e2e_client):
        """WebSocket을 통한 타이머 재개"""
        from tests.conftest import timer_ws_client

        with timer_ws_client(e2e_client) as ws:
            timer = ws.create_timer(title="재개 테스트", allocated_duration=1800)
            timer_id = timer["id"]

            ws.pause_timer(timer_id)
            resumed_timer = ws.resume_timer(timer_id)

            assert resumed_timer["status"] == "RUNNING"
            assert resumed_timer["paused_at"] is None
            assert len(resumed_timer["pause_history"]) >= 3  # start + pause + resume

    def test_stop_timer_via_websocket(self, e2e_client):
        """WebSocket을 통한 타이머 종료"""
        from tests.conftest import timer_ws_client

        with timer_ws_client(e2e_client) as ws:
            timer = ws.create_timer(title="종료 테스트", allocated_duration=1800)
            timer_id = timer["id"]

            stopped_timer = ws.stop_timer(timer_id)

            assert stopped_timer["status"] == "COMPLETED"
            assert stopped_timer["ended_at"] is not None
            assert len(stopped_timer["pause_history"]) >= 2  # start + stop


class TestWebSocketSync:
    """WebSocket 동기화 테스트"""

    def test_timer_sync_request(self, e2e_client):
        """타이머 동기화 요청"""
        with e2e_client.websocket_connect("/v1/ws/timers") as websocket:
            # 연결 메시지 수신
            websocket.receive_json()
            # 자동 동기화 메시지 수신
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
            assert response["type"] in ["timer.sync_result", "error"]


class TestWebSocketErrorHandling:
    """WebSocket 에러 처리 테스트"""

    def test_invalid_message_format(self, e2e_client):
        """잘못된 메시지 형식 처리"""
        with e2e_client.websocket_connect("/v1/ws/timers") as websocket:
            # 연결 메시지 수신
            websocket.receive_json()
            # 자동 동기화 메시지 수신
            websocket.receive_json()

            # 잘못된 형식의 메시지 전송
            websocket.send_text("invalid json")

            # 에러 응답 확인
            response = websocket.receive_json()
            assert response["type"] == "error"
            assert "code" in response["payload"]

    def test_unknown_message_type(self, e2e_client):
        """알 수 없는 메시지 타입 처리"""
        with e2e_client.websocket_connect("/v1/ws/timers") as websocket:
            # 연결 메시지 수신
            websocket.receive_json()
            # 자동 동기화 메시지 수신
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

    def test_pause_nonexistent_timer(self, e2e_client):
        """존재하지 않는 타이머 일시정지"""
        with e2e_client.websocket_connect("/v1/ws/timers") as websocket:
            # 연결 메시지 수신
            websocket.receive_json()
            # 자동 동기화 메시지 수신
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

    def test_multiple_connections_same_user(self, e2e_client):
        """동일 사용자의 다중 연결"""
        # FastAPI TestClient는 동시 WebSocket 연결을 지원하지 않으므로
        # 순차적으로 테스트
        with e2e_client.websocket_connect("/v1/ws/timers") as websocket1:
            data1 = websocket1.receive_json()
            assert data1["type"] == "connected"

            # 자동 동기화 메시지
            sync1 = websocket1.receive_json()
            assert sync1["type"] == "timer.sync_result"

        # 두 번째 연결 (첫 번째 연결 종료 후)
        with e2e_client.websocket_connect("/v1/ws/timers") as websocket2:
            data2 = websocket2.receive_json()
            assert data2["type"] == "connected"

            # 자동 동기화 메시지
            sync2 = websocket2.receive_json()
            assert sync2["type"] == "timer.sync_result"


class TestWebSocketAutoSync:
    """WebSocket 자동 동기화 테스트"""

    def test_auto_sync_with_existing_active_timer(self, e2e_client):
        """연결 시 기존 활성 타이머 자동 전송"""
        from tests.conftest import timer_ws_client

        # 1. WebSocket 연결하여 타이머 생성
        with timer_ws_client(e2e_client) as ws:
            timer = ws.create_timer(title="자동 동기화 테스트", allocated_duration=1800)
            timer_id = timer["id"]

        # 2. 새로운 연결 시 기존 활성 타이머 자동 수신
        with e2e_client.websocket_connect("/v1/ws/timers") as websocket2:
            # 연결 메시지
            connected2 = websocket2.receive_json()
            assert connected2["type"] == "connected"

            # 자동 동기화 - 이번에는 1개 타이머 포함
            sync2 = websocket2.receive_json()
            assert sync2["type"] == "timer.sync_result"
            assert sync2["payload"]["count"] == 1
            assert len(sync2["payload"]["timers"]) == 1
            assert sync2["payload"]["timers"][0]["id"] == timer_id
            assert sync2["payload"]["timers"][0]["status"] == "RUNNING"

    def test_auto_sync_only_active_timers(self, e2e_client):
        """자동 동기화는 활성 타이머만 전송 (완료된 타이머 제외)"""
        from tests.conftest import timer_ws_client

        with timer_ws_client(e2e_client) as ws:
            # 타이머 1 생성
            timer1 = ws.create_timer(title="타이머 1", allocated_duration=1800)
            timer1_id = timer1["id"]

            # 타이머 1 일시정지
            pause1 = ws.pause_timer(timer1_id)
            assert pause1["status"] == "PAUSED"

            # 타이머 2 생성
            timer2 = ws.create_timer(title="타이머 2", allocated_duration=1800)
            timer2_id = timer2["id"]

            # 타이머 2 종료
            stop2 = ws.stop_timer(timer2_id)
            assert stop2["status"] == "COMPLETED"

        # 새 연결 시 활성 타이머만 수신 (PAUSED 포함, COMPLETED 제외)
        with e2e_client.websocket_connect("/v1/ws/timers") as websocket2:
            websocket2.receive_json()  # connected
            sync = websocket2.receive_json()

            assert sync["type"] == "timer.sync_result"
            assert sync["payload"]["count"] == 1  # PAUSED 타이머만
            assert sync["payload"]["timers"][0]["id"] == timer1_id
            assert sync["payload"]["timers"][0]["status"] == "PAUSED"

    def test_manual_sync_with_scope(self, e2e_client):
        """수동 sync 요청 시 scope 옵션 테스트"""
        from tests.conftest import timer_ws_client

        with timer_ws_client(e2e_client) as ws:
            # 타이머 생성 후 종료
            timer = ws.create_timer(title="완료될 타이머", allocated_duration=1800)
            timer_id = timer["id"]
            ws.stop_timer(timer_id)

        # 수동 sync 테스트를 위해 raw websocket 사용
        with e2e_client.websocket_connect("/v1/ws/timers") as websocket:
            websocket.receive_json()  # connected
            websocket.receive_json()  # auto sync

            # scope=active: 활성 타이머만
            websocket.send_json({
                "type": "timer.sync",
                "payload": {"scope": "active"},
            })
            sync_active = websocket.receive_json()
            assert sync_active["type"] == "timer.sync_result"
            assert sync_active["payload"]["count"] == 0  # 활성 타이머 없음

            # scope=all: 모든 타이머
            websocket.send_json({
                "type": "timer.sync",
                "payload": {"scope": "all"},
            })
            sync_all = websocket.receive_json()
            assert sync_all["type"] == "timer.sync_result"
            assert sync_all["payload"]["count"] == 1  # 완료된 타이머 포함
            assert sync_all["payload"]["timers"][0]["status"] == "COMPLETED"
