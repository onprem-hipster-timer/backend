"""
WebSocket Timer pause_history 상세 테스트

타이머의 pause_history 필드에 대한 상세 검증
"""
import os
from datetime import datetime

import pytest

# 테스트 환경 설정
os.environ["OIDC_ENABLED"] = "false"
os.environ["RATE_LIMIT_ENABLED"] = "false"


class TestWebSocketPauseHistory:
    """pause_history 필드 상세 검증 테스트"""

    def test_pause_history_on_create(self, e2e_client):
        """타이머 생성 시 pause_history 초기 구조 검증"""
        from tests.conftest import timer_ws_client

        with timer_ws_client(e2e_client) as ws:
            timer = ws.create_timer(title="히스토리 테스트", allocated_duration=1800)

            # pause_history 검증
            assert "pause_history" in timer
            assert len(timer["pause_history"]) == 1
            assert timer["pause_history"][0]["action"] == "start"
            assert "at" in timer["pause_history"][0]

    def test_pause_history_full_lifecycle(self, e2e_client):
        """전체 라이프사이클 pause_history 추적"""
        from tests.conftest import timer_ws_client

        with timer_ws_client(e2e_client) as ws:
            # 1. 생성 (start)
            timer = ws.create_timer(title="라이프사이클 테스트", allocated_duration=1800)
            timer_id = timer["id"]
            assert len(timer["pause_history"]) == 1
            assert timer["pause_history"][0]["action"] == "start"

            # 2. 일시정지 (pause)
            paused_timer = ws.pause_timer(timer_id)
            assert len(paused_timer["pause_history"]) == 2
            assert paused_timer["pause_history"][1]["action"] == "pause"

            # 3. 재개 (resume)
            resumed_timer = ws.resume_timer(timer_id)
            assert len(resumed_timer["pause_history"]) == 3
            assert resumed_timer["pause_history"][2]["action"] == "resume"

            # 4. 다시 일시정지
            paused2_timer = ws.pause_timer(timer_id)
            assert len(paused2_timer["pause_history"]) == 4
            assert paused2_timer["pause_history"][3]["action"] == "pause"

            # 5. 다시 재개
            resumed2_timer = ws.resume_timer(timer_id)
            assert len(resumed2_timer["pause_history"]) == 5
            assert resumed2_timer["pause_history"][4]["action"] == "resume"

            # 6. 종료 (stop)
            stopped_timer = ws.stop_timer(timer_id)
            assert len(stopped_timer["pause_history"]) == 6
            assert stopped_timer["pause_history"][5]["action"] == "stop"

            # 전체 히스토리 순서 검증
            expected_actions = ["start", "pause", "resume", "pause", "resume", "stop"]
            actual_actions = [h["action"] for h in stopped_timer["pause_history"]]
            assert actual_actions == expected_actions

    def test_pause_history_timestamps_valid(self, e2e_client):
        """pause_history 타임스탬프 유효성 및 순서 검증"""
        from tests.conftest import timer_ws_client

        with timer_ws_client(e2e_client) as ws:
            # 타이머 생성
            timer = ws.create_timer(title="타임스탬프 테스트", allocated_duration=1800)
            timer_id = timer["id"]

            # 일시정지
            paused_timer = ws.pause_timer(timer_id)
            history = paused_timer["pause_history"]

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
                t2 = datetime.fromisoformat(history[i + 1]["at"].replace("Z", "+00:00"))
                assert t1 <= t2, f"Timestamps out of order: {history[i]['at']} > {history[i + 1]['at']}"
