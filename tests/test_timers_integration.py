"""
Timer Integration Tests

DB를 포함한 타이머 통합 테스트
"""
import pytest
from datetime import datetime, UTC
from uuid import uuid4

from app.domain.timer.service import TimerService
from app.domain.timer.schema.dto import TimerCreate, TimerUpdate
from app.domain.timer.exceptions import TimerNotFoundError
from app.domain.schedule.service import ScheduleService
from app.domain.schedule.schema.dto import ScheduleCreate
from app.core.constants import TimerStatus


@pytest.mark.integration
def test_create_and_get_timer_integration(test_session):
    """DB를 포함한 타이머 생성 및 조회 통합 테스트"""
    # 1. 일정 생성
    schedule_service = ScheduleService(test_session)
    schedule_data = ScheduleCreate(
        title="통합 테스트 일정",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
    )
    schedule = schedule_service.create_schedule(schedule_data)
    
    # 2. 타이머 생성
    timer_service = TimerService(test_session)
    timer_data = TimerCreate(
        schedule_id=schedule.id,
        title="통합 테스트 타이머",
        allocated_duration=1800,
    )
    created_timer = timer_service.create_timer(timer_data)
    timer_id = created_timer.id
    
    # 3. DB에서 실제로 저장되었는지 확인
    saved_timer = timer_service.get_timer(timer_id)
    assert saved_timer is not None
    assert saved_timer.id == timer_id
    assert saved_timer.title == "통합 테스트 타이머"
    assert saved_timer.status == TimerStatus.RUNNING.value


@pytest.mark.integration
def test_timer_workflow_integration(test_session):
    """타이머 전체 워크플로우 통합 테스트"""
    # 1. 일정 생성
    schedule_service = ScheduleService(test_session)
    schedule_data = ScheduleCreate(
        title="워크플로우 테스트 일정",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
    )
    schedule = schedule_service.create_schedule(schedule_data)
    
    # 2. 타이머 생성
    timer_service = TimerService(test_session)
    timer_data = TimerCreate(
        schedule_id=schedule.id,
        title="워크플로우 타이머",
        allocated_duration=1800,
    )
    timer = timer_service.create_timer(timer_data)
    timer_id = timer.id
    
    # 3. 타이머 일시정지
    paused_timer = timer_service.pause_timer(timer_id)
    assert paused_timer.status == TimerStatus.PAUSED.value
    elapsed_when_paused = paused_timer.elapsed_time
    
    # 4. 타이머 재개
    resumed_timer = timer_service.resume_timer(timer_id)
    assert resumed_timer.status == TimerStatus.RUNNING.value
    
    # 5. 타이머 종료
    stopped_timer = timer_service.stop_timer(timer_id)
    assert stopped_timer.status == TimerStatus.COMPLETED.value
    assert stopped_timer.ended_at is not None
    
    # 6. 타이머 조회 확인
    final_timer = timer_service.get_timer(timer_id)
    assert final_timer.status == TimerStatus.COMPLETED.value


@pytest.mark.integration
def test_multiple_timers_per_schedule_integration(test_session):
    """일정당 여러 타이머 생성 통합 테스트"""
    # 1. 일정 생성
    schedule_service = ScheduleService(test_session)
    schedule_data = ScheduleCreate(
        title="다중 타이머 테스트 일정",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
    )
    schedule = schedule_service.create_schedule(schedule_data)
    
    # 2. 여러 타이머 생성
    timer_service = TimerService(test_session)
    timer_ids = []
    
    for i in range(3):
        timer_data = TimerCreate(
            schedule_id=schedule.id,
            title=f"타이머 {i+1}",
            allocated_duration=1800 * (i + 1),
        )
        timer = timer_service.create_timer(timer_data)
        timer_ids.append(timer.id)
    
    # 3. 일정의 모든 타이머 조회
    timers = timer_service.get_timers_by_schedule(schedule.id)
    retrieved_ids = [t.id for t in timers]
    
    # 모든 타이머가 조회되어야 함
    for timer_id in timer_ids:
        assert timer_id in retrieved_ids


@pytest.mark.integration
def test_timer_schedule_relationship_integration(test_session):
    """타이머-일정 관계 통합 테스트"""
    # 1. 일정 생성
    schedule_service = ScheduleService(test_session)
    schedule_data = ScheduleCreate(
        title="관계 테스트 일정",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
    )
    schedule = schedule_service.create_schedule(schedule_data)
    
    # 2. 타이머 생성
    timer_service = TimerService(test_session)
    timer_data = TimerCreate(
        schedule_id=schedule.id,
        allocated_duration=1800,
    )
    timer = timer_service.create_timer(timer_data)
    
    # 3. 일정 조회 후 타이머 확인
    retrieved_schedule = schedule_service.get_schedule(schedule.id)
    assert retrieved_schedule.id == schedule.id
    
    # 4. 타이머의 schedule_id 확인
    retrieved_timer = timer_service.get_timer(timer.id)
    assert retrieved_timer.schedule_id == schedule.id


@pytest.mark.integration
def test_timer_include_schedule_false_integration(test_session):
    """타이머 조회 시 include_schedule=False일 때 schedule이 None인지 통합 테스트"""
    from app.domain.timer.schema.dto import TimerRead
    from app.domain.schedule.schema.dto import ScheduleRead
    
    # 1. 일정 생성
    schedule_service = ScheduleService(test_session)
    schedule_data = ScheduleCreate(
        title="include_schedule False 테스트 일정",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
    )
    schedule = schedule_service.create_schedule(schedule_data)
    
    # 2. 타이머 생성
    timer_service = TimerService(test_session)
    timer_data = TimerCreate(
        schedule_id=schedule.id,
        title="include_schedule False 테스트 타이머",
        allocated_duration=1800,
    )
    timer = timer_service.create_timer(timer_data)
    
    # 3. include_schedule=False로 TimerRead 생성
    timer_read = TimerRead.from_model(
        timer,
        include_schedule=False,
    )
    
    # 4. schedule이 None인지 확인
    assert timer_read.schedule is None
    assert timer_read.id == timer.id
    assert timer_read.schedule_id == schedule.id


@pytest.mark.integration
def test_timer_include_schedule_true_integration(test_session):
    """타이머 조회 시 include_schedule=True일 때 schedule이 포함되는지 통합 테스트"""
    from app.domain.timer.schema.dto import TimerRead
    from app.domain.schedule.schema.dto import ScheduleRead
    
    # 1. 일정 생성
    schedule_service = ScheduleService(test_session)
    schedule_data = ScheduleCreate(
        title="include_schedule True 테스트 일정",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
    )
    schedule = schedule_service.create_schedule(schedule_data)
    
    # 2. 타이머 생성
    timer_service = TimerService(test_session)
    timer_data = TimerCreate(
        schedule_id=schedule.id,
        title="include_schedule True 테스트 타이머",
        allocated_duration=1800,
    )
    timer = timer_service.create_timer(timer_data)
    
    # 3. 스케줄 정보 조회
    schedule_read = ScheduleRead.model_validate(schedule)
    
    # 4. include_schedule=True로 TimerRead 생성
    timer_read = TimerRead.from_model(
        timer,
        include_schedule=True,
        schedule=schedule_read,
    )
    
    # 5. schedule이 포함되어 있는지 확인
    assert timer_read.schedule is not None
    assert timer_read.schedule.id == schedule.id
    assert timer_read.schedule.title == schedule.title
    assert timer_read.id == timer.id
    assert timer_read.schedule_id == schedule.id
