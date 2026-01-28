"""
Timer pause_history 테스트

타이머의 일시정지/재개 이력이 올바르게 저장되는지 테스트합니다.
"""
import pytest

from app.core.constants import TimerStatus
from app.domain.timer.schema.dto import TimerCreate
from app.domain.timer.service import TimerService


class TestPauseHistoryOnCreate:
    """타이머 생성 시 pause_history 테스트"""

    def test_create_timer_has_start_event(self, test_session, sample_schedule, test_user):
        """타이머 생성 시 start 이벤트가 기록되어야 함"""
        timer_data = TimerCreate(
            schedule_id=sample_schedule.id,
            title="테스트 타이머",
            allocated_duration=1800,
        )

        service = TimerService(test_session, test_user)
        timer = service.create_timer(timer_data)

        assert timer.pause_history is not None
        assert len(timer.pause_history) == 1
        assert timer.pause_history[0]["action"] == "start"
        assert "at" in timer.pause_history[0]

    def test_create_independent_timer_has_start_event(self, test_session, test_user):
        """독립 타이머 생성 시에도 start 이벤트가 기록되어야 함"""
        timer_data = TimerCreate(
            title="독립 타이머",
            allocated_duration=600,
        )

        service = TimerService(test_session, test_user)
        timer = service.create_timer(timer_data)

        assert len(timer.pause_history) == 1
        assert timer.pause_history[0]["action"] == "start"


class TestPauseHistoryOnPause:
    """타이머 일시정지 시 pause_history 테스트"""

    def test_pause_adds_pause_event(self, test_session, sample_timer, test_user):
        """일시정지 시 pause 이벤트가 추가되어야 함"""
        service = TimerService(test_session, test_user)

        paused_timer = service.pause_timer(sample_timer.id)

        # start + pause = 2개 이벤트
        assert len(paused_timer.pause_history) == 2
        assert paused_timer.pause_history[0]["action"] == "start"
        assert paused_timer.pause_history[1]["action"] == "pause"
        assert "at" in paused_timer.pause_history[1]
        assert "elapsed" in paused_timer.pause_history[1]

    def test_pause_records_elapsed_time(self, test_session, sample_timer, test_user):
        """일시정지 시 경과 시간이 기록되어야 함"""
        service = TimerService(test_session, test_user)

        paused_timer = service.pause_timer(sample_timer.id)

        pause_event = paused_timer.pause_history[1]
        assert pause_event["elapsed"] == paused_timer.elapsed_time


class TestPauseHistoryOnResume:
    """타이머 재개 시 pause_history 테스트"""

    def test_resume_adds_resume_event(self, test_session, sample_timer, test_user):
        """재개 시 resume 이벤트가 추가되어야 함"""
        service = TimerService(test_session, test_user)

        # 먼저 일시정지
        service.pause_timer(sample_timer.id)

        # 재개
        resumed_timer = service.resume_timer(sample_timer.id)

        # start + pause + resume = 3개 이벤트
        assert len(resumed_timer.pause_history) == 3
        assert resumed_timer.pause_history[0]["action"] == "start"
        assert resumed_timer.pause_history[1]["action"] == "pause"
        assert resumed_timer.pause_history[2]["action"] == "resume"
        assert "at" in resumed_timer.pause_history[2]


class TestPauseHistoryMultipleCycles:
    """다중 일시정지/재개 사이클 테스트"""

    def test_multiple_pause_resume_cycles(self, test_session, sample_timer, test_user):
        """여러 번의 일시정지/재개가 모두 기록되어야 함"""
        service = TimerService(test_session, test_user)

        # 첫 번째 사이클
        service.pause_timer(sample_timer.id)
        service.resume_timer(sample_timer.id)

        # 두 번째 사이클
        service.pause_timer(sample_timer.id)
        timer = service.resume_timer(sample_timer.id)

        # start + pause + resume + pause + resume = 5개 이벤트
        assert len(timer.pause_history) == 5
        assert timer.pause_history[0]["action"] == "start"
        assert timer.pause_history[1]["action"] == "pause"
        assert timer.pause_history[2]["action"] == "resume"
        assert timer.pause_history[3]["action"] == "pause"
        assert timer.pause_history[4]["action"] == "resume"

    def test_pause_history_preserves_all_timestamps(self, test_session, sample_timer, test_user):
        """모든 이벤트의 타임스탬프가 저장되어야 함"""
        service = TimerService(test_session, test_user)

        service.pause_timer(sample_timer.id)
        service.resume_timer(sample_timer.id)
        timer = service.pause_timer(sample_timer.id)

        # 모든 이벤트에 타임스탬프가 있어야 함
        for event in timer.pause_history:
            assert "at" in event
            assert event["at"] is not None


class TestPauseHistoryOnStop:
    """타이머 종료 시 pause_history 테스트"""

    def test_stop_adds_stop_event(self, test_session, sample_timer, test_user):
        """종료 시 stop 이벤트가 추가되어야 함"""
        service = TimerService(test_session, test_user)

        stopped_timer = service.stop_timer(sample_timer.id)

        # start + stop = 2개 이벤트
        assert len(stopped_timer.pause_history) == 2
        assert stopped_timer.pause_history[0]["action"] == "start"
        assert stopped_timer.pause_history[1]["action"] == "stop"
        assert "at" in stopped_timer.pause_history[1]
        assert "elapsed" in stopped_timer.pause_history[1]

    def test_stop_from_paused_adds_stop_event(self, test_session, sample_timer, test_user):
        """일시정지 상태에서 종료 시 stop 이벤트가 추가되어야 함"""
        service = TimerService(test_session, test_user)

        # 일시정지
        service.pause_timer(sample_timer.id)

        # 종료
        stopped_timer = service.stop_timer(sample_timer.id)

        # start + pause + stop = 3개 이벤트
        assert len(stopped_timer.pause_history) == 3
        assert stopped_timer.pause_history[2]["action"] == "stop"

    def test_stop_records_final_elapsed_time(self, test_session, sample_timer, test_user):
        """종료 시 최종 경과 시간이 기록되어야 함"""
        service = TimerService(test_session, test_user)

        stopped_timer = service.stop_timer(sample_timer.id)

        stop_event = stopped_timer.pause_history[-1]
        assert stop_event["elapsed"] == stopped_timer.elapsed_time


class TestPauseHistoryOnCancel:
    """타이머 취소 시 pause_history 테스트"""

    def test_cancel_adds_cancel_event(self, test_session, sample_timer, test_user):
        """취소 시 cancel 이벤트가 추가되어야 함"""
        service = TimerService(test_session, test_user)

        cancelled_timer = service.cancel_timer(sample_timer.id)

        # start + cancel = 2개 이벤트
        assert len(cancelled_timer.pause_history) == 2
        assert cancelled_timer.pause_history[0]["action"] == "start"
        assert cancelled_timer.pause_history[1]["action"] == "cancel"
        assert "at" in cancelled_timer.pause_history[1]
        assert "elapsed" in cancelled_timer.pause_history[1]


class TestGetPauseHistory:
    """pause_history 조회 테스트"""

    def test_get_pause_history_returns_list(self, test_session, sample_timer, test_user):
        """pause_history 조회가 리스트를 반환해야 함"""
        service = TimerService(test_session, test_user)

        history = service.get_pause_history(sample_timer.id)

        assert isinstance(history, list)
        assert len(history) == 1  # start 이벤트만 있음

    def test_get_pause_history_after_pause_resume(self, test_session, sample_timer, test_user):
        """일시정지/재개 후 전체 이력을 조회할 수 있어야 함"""
        service = TimerService(test_session, test_user)

        service.pause_timer(sample_timer.id)
        service.resume_timer(sample_timer.id)

        history = service.get_pause_history(sample_timer.id)

        assert len(history) == 3  # start + pause + resume
        assert history[0]["action"] == "start"
        assert history[1]["action"] == "pause"
        assert history[2]["action"] == "resume"


class TestPauseHistoryDTO:
    """TimerRead DTO에 pause_history 포함 테스트"""

    def test_timer_read_includes_pause_history(self, test_session, sample_timer, test_user):
        """TimerRead DTO에 pause_history가 포함되어야 함"""
        service = TimerService(test_session, test_user)

        service.pause_timer(sample_timer.id)
        timer = service.resume_timer(sample_timer.id)

        dto = service.to_read_dto(timer)

        assert dto.pause_history is not None
        assert len(dto.pause_history) == 3
        assert dto.pause_history[0]["action"] == "start"
        assert dto.pause_history[1]["action"] == "pause"
        assert dto.pause_history[2]["action"] == "resume"

    def test_independent_timer_dto_includes_pause_history(self, test_session, test_user):
        """독립 타이머 DTO에도 pause_history가 포함되어야 함"""
        service = TimerService(test_session, test_user)

        timer = service.create_timer(TimerCreate(
            title="독립 타이머",
            allocated_duration=600,
        ))

        dto = service.to_read_dto(timer)

        assert dto.pause_history is not None
        assert len(dto.pause_history) == 1
        assert dto.pause_history[0]["action"] == "start"
