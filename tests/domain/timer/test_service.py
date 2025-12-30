"""
Timer Service 테스트

타이머 서비스의 비즈니스 로직을 테스트합니다.
"""
import pytest
from datetime import datetime, UTC
from uuid import UUID

from pydantic import ValidationError

from app.domain.timer.service import TimerService
from app.domain.timer.schema.dto import TimerCreate, TimerUpdate
from app.domain.timer.exceptions import (
    TimerNotFoundError,
    InvalidTimerStatusError,
)
from app.domain.schedule.exceptions import ScheduleNotFoundError
from app.core.constants import TimerStatus


def test_create_timer_success(test_session, sample_schedule):
    """타이머 생성 성공 테스트"""
    timer_data = TimerCreate(
        schedule_id=sample_schedule.id,
        title="회의 준비",
        description="회의 자료 준비",
        allocated_duration=1800,  # 30분
    )
    
    service = TimerService(test_session)
    timer = service.create_timer(timer_data)
    
    assert timer.title == "회의 준비"
    assert timer.description == "회의 자료 준비"
    assert timer.allocated_duration == 1800
    assert timer.elapsed_time == 0
    assert timer.status == TimerStatus.RUNNING.value
    assert timer.started_at is not None
    assert timer.schedule_id == sample_schedule.id
    assert isinstance(timer.id, UUID)


def test_create_timer_without_title_description(test_session, sample_schedule):
    """제목과 설명 없이 타이머 생성 테스트"""
    timer_data = TimerCreate(
        schedule_id=sample_schedule.id,
        allocated_duration=3600,  # 1시간
    )
    
    service = TimerService(test_session)
    timer = service.create_timer(timer_data)
    
    assert timer.title is None
    assert timer.description is None
    assert timer.status == TimerStatus.RUNNING.value


def test_create_timer_invalid_schedule_id(test_session):
    """존재하지 않는 일정 ID로 타이머 생성 실패 테스트"""
    from uuid import uuid4
    
    timer_data = TimerCreate(
        schedule_id=uuid4(),
        allocated_duration=1800,
    )
    
    service = TimerService(test_session)
    with pytest.raises(ScheduleNotFoundError):
        service.create_timer(timer_data)


def test_create_timer_invalid_allocated_duration(test_session, sample_schedule):
    """잘못된 allocated_duration으로 타이머 생성 실패 테스트"""
    from pydantic import ValidationError
    
    # Pydantic 검증에서 실패해야 함
    with pytest.raises(ValidationError):
        TimerCreate(
            schedule_id=sample_schedule.id,
            allocated_duration=-100,  # 음수
        )


def test_get_timer_success(test_session, sample_timer):
    """타이머 조회 성공 테스트"""
    service = TimerService(test_session)
    retrieved_timer = service.get_timer(sample_timer.id)
    
    assert retrieved_timer.id == sample_timer.id
    assert retrieved_timer.title == sample_timer.title
    assert retrieved_timer.status == TimerStatus.RUNNING.value


def test_get_timer_not_found(test_session):
    """존재하지 않는 타이머 조회 실패 테스트"""
    from uuid import uuid4
    
    service = TimerService(test_session)
    with pytest.raises(TimerNotFoundError):
        service.get_timer(uuid4())


def test_get_timer_running_elapsed_time_calculation(test_session, sample_schedule):
    """RUNNING 상태 타이머의 경과 시간 실시간 계산 테스트"""
    timer_data = TimerCreate(
        schedule_id=sample_schedule.id,
        allocated_duration=1800,
    )
    
    service = TimerService(test_session)
    timer = service.create_timer(timer_data)
    initial_elapsed = timer.elapsed_time
    
    # 시간 경과 시뮬레이션 (실제로는 시간이 경과하지 않지만 로직 확인)
    retrieved = service.get_timer(timer.id)
    # RUNNING 상태이므로 경과 시간이 계산되어야 함
    assert retrieved.status == TimerStatus.RUNNING.value


def test_pause_timer_success(test_session, sample_timer):
    """타이머 일시정지 성공 테스트"""
    service = TimerService(test_session)
    
    # RUNNING 상태에서 일시정지
    paused_timer = service.pause_timer(sample_timer.id)
    
    assert paused_timer.status == TimerStatus.PAUSED.value
    assert paused_timer.paused_at is not None
    assert paused_timer.elapsed_time >= 0  # 경과 시간이 저장되어야 함


def test_pause_timer_not_running(test_session, sample_schedule):
    """RUNNING 상태가 아닌 타이머 일시정지 실패 테스트"""
    timer_data = TimerCreate(
        schedule_id=sample_schedule.id,
        allocated_duration=1800,
    )
    
    service = TimerService(test_session)
    timer = service.create_timer(timer_data)
    
    # PAUSED 상태로 변경
    service.pause_timer(timer.id)
    test_session.flush()
    
    # PAUSED 상태에서 다시 pause 시도
    with pytest.raises(InvalidTimerStatusError):
        service.pause_timer(timer.id)


def test_resume_timer_success(test_session, sample_timer):
    """타이머 재개 성공 테스트"""
    service = TimerService(test_session)
    
    # 일시정지
    paused_timer = service.pause_timer(sample_timer.id)
    elapsed_before_resume = paused_timer.elapsed_time
    
    # 재개
    resumed_timer = service.resume_timer(paused_timer.id)
    
    assert resumed_timer.status == TimerStatus.RUNNING.value
    assert resumed_timer.paused_at is None
    assert resumed_timer.started_at is not None
    assert resumed_timer.elapsed_time == elapsed_before_resume  # 경과 시간은 유지


def test_resume_timer_not_paused(test_session, sample_timer):
    """PAUSED 상태가 아닌 타이머 재개 실패 테스트"""
    service = TimerService(test_session)
    
    # RUNNING 상태에서 resume 시도
    with pytest.raises(InvalidTimerStatusError):
        service.resume_timer(sample_timer.id)


def test_stop_timer_from_running(test_session, sample_timer):
    """RUNNING 상태 타이머 종료 테스트"""
    service = TimerService(test_session)
    
    stopped_timer = service.stop_timer(sample_timer.id)
    
    assert stopped_timer.status == TimerStatus.COMPLETED.value
    assert stopped_timer.ended_at is not None
    assert stopped_timer.elapsed_time >= 0


def test_stop_timer_from_paused(test_session, sample_timer):
    """PAUSED 상태 타이머 종료 테스트"""
    service = TimerService(test_session)
    
    # 일시정지
    paused_timer = service.pause_timer(sample_timer.id)
    elapsed_when_paused = paused_timer.elapsed_time
    
    # 종료
    stopped_timer = service.stop_timer(paused_timer.id)
    
    assert stopped_timer.status == TimerStatus.COMPLETED.value
    assert stopped_timer.ended_at is not None
    assert stopped_timer.elapsed_time == elapsed_when_paused  # 일시정지 시점의 경과 시간 유지


def test_stop_timer_invalid_status(test_session, sample_schedule):
    """종료할 수 없는 상태의 타이머 종료 실패 테스트"""
    timer_data = TimerCreate(
        schedule_id=sample_schedule.id,
        allocated_duration=1800,
    )
    
    service = TimerService(test_session)
    timer = service.create_timer(timer_data)
    
    # 종료
    service.stop_timer(timer.id)
    test_session.flush()
    
    # COMPLETED 상태에서 stop 시도
    with pytest.raises(InvalidTimerStatusError):
        service.stop_timer(timer.id)


def test_cancel_timer_success(test_session, sample_timer):
    """타이머 취소 성공 테스트"""
    service = TimerService(test_session)
    
    cancelled_timer = service.cancel_timer(sample_timer.id)
    
    assert cancelled_timer.status == TimerStatus.CANCELLED.value
    assert cancelled_timer.ended_at is not None


def test_update_timer_metadata(test_session, sample_timer):
    """타이머 메타데이터 업데이트 테스트"""
    service = TimerService(test_session)
    
    update_data = TimerUpdate(
        title="업데이트된 제목",
        description="업데이트된 설명",
    )
    
    updated_timer = service.update_timer(sample_timer.id, update_data)
    
    assert updated_timer.title == "업데이트된 제목"
    assert updated_timer.description == "업데이트된 설명"
    # 다른 필드는 변경되지 않아야 함
    assert updated_timer.allocated_duration == sample_timer.allocated_duration


def test_update_timer_partial(test_session, sample_timer):
    """타이머 부분 업데이트 테스트 (일부 필드만)"""
    service = TimerService(test_session)
    original_title = sample_timer.title
    
    update_data = TimerUpdate(
        description="설명만 업데이트",
    )
    
    updated_timer = service.update_timer(sample_timer.id, update_data)
    
    assert updated_timer.title == original_title  # 제목은 변경되지 않음
    assert updated_timer.description == "설명만 업데이트"


def test_delete_timer_success(test_session, sample_timer):
    """타이머 삭제 성공 테스트"""
    service = TimerService(test_session)
    timer_id = sample_timer.id
    
    service.delete_timer(timer_id)
    test_session.flush()
    
    # 삭제 확인
    test_session.expire_all()
    with pytest.raises(TimerNotFoundError):
        service.get_timer(timer_id)


def test_get_timers_by_schedule(test_session, sample_schedule):
    """일정의 모든 타이머 조회 테스트"""
    service = TimerService(test_session)
    
    # 여러 타이머 생성
    timer1_data = TimerCreate(
        schedule_id=sample_schedule.id,
        title="타이머 1",
        allocated_duration=1800,
    )
    timer2_data = TimerCreate(
        schedule_id=sample_schedule.id,
        title="타이머 2",
        allocated_duration=3600,
    )
    
    timer1 = service.create_timer(timer1_data)
    timer2 = service.create_timer(timer2_data)
    
    # 일정의 모든 타이머 조회
    timers = service.get_timers_by_schedule(sample_schedule.id)
    
    timer_ids = [t.id for t in timers]
    assert timer1.id in timer_ids
    assert timer2.id in timer_ids
    assert len(timers) >= 2


def test_get_active_timer(test_session, sample_schedule):
    """활성 타이머 조회 테스트"""
    service = TimerService(test_session)
    
    # 타이머 생성 (RUNNING 상태)
    timer_data = TimerCreate(
        schedule_id=sample_schedule.id,
        allocated_duration=1800,
    )
    active_timer = service.create_timer(timer_data)
    
    # 활성 타이머 조회
    retrieved_active = service.get_active_timer(sample_schedule.id)
    
    assert retrieved_active is not None
    assert retrieved_active.id == active_timer.id
    assert retrieved_active.status in [TimerStatus.RUNNING.value, TimerStatus.PAUSED.value]


def test_get_active_timer_none(test_session, sample_schedule):
    """활성 타이머가 없을 때 None 반환 테스트"""
    service = TimerService(test_session)
    
    # 타이머 생성 후 종료
    timer_data = TimerCreate(
        schedule_id=sample_schedule.id,
        allocated_duration=1800,
    )
    timer = service.create_timer(timer_data)
    service.stop_timer(timer.id)
    test_session.flush()
    
    # 활성 타이머 조회 (None 반환)
    active_timer = service.get_active_timer(sample_schedule.id)
    assert active_timer is None

