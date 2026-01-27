"""
Timer Service 테스트

타이머 서비스의 비즈니스 로직을 테스트합니다.
"""
from uuid import UUID

import pytest

from app.core.constants import TimerStatus
from app.domain.schedule.exceptions import ScheduleNotFoundError
from app.domain.timer.exceptions import (
    TimerNotFoundError,
    InvalidTimerStatusError,
)
from app.domain.timer.schema.dto import TimerCreate, TimerUpdate
from app.domain.timer.service import TimerService
from app.domain.todo.exceptions import TodoNotFoundError


def test_create_timer_success(test_session, sample_schedule, test_user):
    """타이머 생성 성공 테스트"""
    timer_data = TimerCreate(
        schedule_id=sample_schedule.id,
        title="회의 준비",
        description="회의 자료 준비",
        allocated_duration=1800,  # 30분
    )

    service = TimerService(test_session, test_user)
    timer = service.create_timer(timer_data)

    assert timer.title == "회의 준비"
    assert timer.description == "회의 자료 준비"
    assert timer.allocated_duration == 1800
    assert timer.elapsed_time == 0
    assert timer.status == TimerStatus.RUNNING.value
    assert timer.started_at is not None
    assert timer.schedule_id == sample_schedule.id
    assert isinstance(timer.id, UUID)


def test_create_timer_without_title_description(test_session, sample_schedule, test_user):
    """제목과 설명 없이 타이머 생성 테스트"""
    timer_data = TimerCreate(
        schedule_id=sample_schedule.id,
        allocated_duration=3600,  # 1시간
    )

    service = TimerService(test_session, test_user)
    timer = service.create_timer(timer_data)

    assert timer.title is None
    assert timer.description is None
    assert timer.status == TimerStatus.RUNNING.value


def test_create_timer_invalid_schedule_id(test_session, test_user):
    """존재하지 않는 일정 ID로 타이머 생성 실패 테스트"""
    from uuid import uuid4

    timer_data = TimerCreate(
        schedule_id=uuid4(),
        allocated_duration=1800,
    )

    service = TimerService(test_session, test_user)
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


def test_get_timer_success(test_session, sample_timer, test_user):
    """타이머 조회 성공 테스트"""
    service = TimerService(test_session, test_user)
    retrieved_timer = service.get_timer(sample_timer.id)

    assert retrieved_timer.id == sample_timer.id
    assert retrieved_timer.title == sample_timer.title
    assert retrieved_timer.status == TimerStatus.RUNNING.value


def test_get_timer_not_found(test_session, test_user):
    """존재하지 않는 타이머 조회 실패 테스트"""
    from uuid import uuid4

    service = TimerService(test_session, test_user)
    with pytest.raises(TimerNotFoundError):
        service.get_timer(uuid4())


def test_get_timer_running_elapsed_time_calculation(test_session, sample_schedule, test_user):
    """RUNNING 상태 타이머의 경과 시간 실시간 계산 테스트"""
    timer_data = TimerCreate(
        schedule_id=sample_schedule.id,
        allocated_duration=1800,
    )

    service = TimerService(test_session, test_user)
    timer = service.create_timer(timer_data)
    initial_elapsed = timer.elapsed_time

    # 시간 경과 시뮬레이션 (실제로는 시간이 경과하지 않지만 로직 확인)
    retrieved = service.get_timer(timer.id)
    # RUNNING 상태이므로 경과 시간이 계산되어야 함
    assert retrieved.status == TimerStatus.RUNNING.value


def test_pause_timer_success(test_session, sample_timer, test_user):
    """타이머 일시정지 성공 테스트"""
    service = TimerService(test_session, test_user)

    # RUNNING 상태에서 일시정지
    paused_timer = service.pause_timer(sample_timer.id)

    assert paused_timer.status == TimerStatus.PAUSED.value
    assert paused_timer.paused_at is not None
    assert paused_timer.elapsed_time >= 0  # 경과 시간이 저장되어야 함


def test_pause_timer_not_running(test_session, sample_schedule, test_user):
    """RUNNING 상태가 아닌 타이머 일시정지 실패 테스트"""
    timer_data = TimerCreate(
        schedule_id=sample_schedule.id,
        allocated_duration=1800,
    )

    service = TimerService(test_session, test_user)
    timer = service.create_timer(timer_data)

    # PAUSED 상태로 변경
    service.pause_timer(timer.id)
    test_session.flush()

    # PAUSED 상태에서 다시 pause 시도
    with pytest.raises(InvalidTimerStatusError):
        service.pause_timer(timer.id)


def test_resume_timer_success(test_session, sample_timer, test_user):
    """타이머 재개 성공 테스트"""
    service = TimerService(test_session, test_user)

    # 일시정지
    paused_timer = service.pause_timer(sample_timer.id)
    elapsed_before_resume = paused_timer.elapsed_time

    # 재개
    resumed_timer = service.resume_timer(paused_timer.id)

    assert resumed_timer.status == TimerStatus.RUNNING.value
    assert resumed_timer.paused_at is None
    assert resumed_timer.started_at is not None
    assert resumed_timer.elapsed_time == elapsed_before_resume  # 경과 시간은 유지


def test_resume_timer_not_paused(test_session, sample_timer, test_user):
    """PAUSED 상태가 아닌 타이머 재개 실패 테스트"""
    service = TimerService(test_session, test_user)

    # RUNNING 상태에서 resume 시도
    with pytest.raises(InvalidTimerStatusError):
        service.resume_timer(sample_timer.id)


def test_stop_timer_from_running(test_session, sample_timer, test_user):
    """RUNNING 상태 타이머 종료 테스트"""
    service = TimerService(test_session, test_user)

    stopped_timer = service.stop_timer(sample_timer.id)

    assert stopped_timer.status == TimerStatus.COMPLETED.value
    assert stopped_timer.ended_at is not None
    assert stopped_timer.elapsed_time >= 0


def test_stop_timer_from_paused(test_session, sample_timer, test_user):
    """PAUSED 상태 타이머 종료 테스트"""
    service = TimerService(test_session, test_user)

    # 일시정지
    paused_timer = service.pause_timer(sample_timer.id)
    elapsed_when_paused = paused_timer.elapsed_time

    # 종료
    stopped_timer = service.stop_timer(paused_timer.id)

    assert stopped_timer.status == TimerStatus.COMPLETED.value
    assert stopped_timer.ended_at is not None
    assert stopped_timer.elapsed_time == elapsed_when_paused  # 일시정지 시점의 경과 시간 유지


def test_stop_timer_invalid_status(test_session, sample_schedule, test_user):
    """종료할 수 없는 상태의 타이머 종료 실패 테스트"""
    timer_data = TimerCreate(
        schedule_id=sample_schedule.id,
        allocated_duration=1800,
    )

    service = TimerService(test_session, test_user)
    timer = service.create_timer(timer_data)

    # 종료
    service.stop_timer(timer.id)
    test_session.flush()

    # COMPLETED 상태에서 stop 시도
    with pytest.raises(InvalidTimerStatusError):
        service.stop_timer(timer.id)


def test_cancel_timer_success(test_session, sample_timer, test_user):
    """타이머 취소 성공 테스트"""
    service = TimerService(test_session, test_user)

    cancelled_timer = service.cancel_timer(sample_timer.id)

    assert cancelled_timer.status == TimerStatus.CANCELLED.value
    assert cancelled_timer.ended_at is not None


def test_update_timer_metadata(test_session, sample_timer, test_user):
    """타이머 메타데이터 업데이트 테스트"""
    service = TimerService(test_session, test_user)

    update_data = TimerUpdate(
        title="업데이트된 제목",
        description="업데이트된 설명",
    )

    updated_timer = service.update_timer(sample_timer.id, update_data)

    assert updated_timer.title == "업데이트된 제목"
    assert updated_timer.description == "업데이트된 설명"
    # 다른 필드는 변경되지 않아야 함
    assert updated_timer.allocated_duration == sample_timer.allocated_duration


def test_update_timer_partial(test_session, sample_timer, test_user):
    """타이머 부분 업데이트 테스트 (일부 필드만)"""
    service = TimerService(test_session, test_user)
    original_title = sample_timer.title

    update_data = TimerUpdate(
        description="설명만 업데이트",
    )

    updated_timer = service.update_timer(sample_timer.id, update_data)

    assert updated_timer.title == original_title  # 제목은 변경되지 않음
    assert updated_timer.description == "설명만 업데이트"


def test_delete_timer_success(test_session, sample_timer, test_user):
    """타이머 삭제 성공 테스트"""
    service = TimerService(test_session, test_user)
    timer_id = sample_timer.id

    service.delete_timer(timer_id)
    test_session.flush()

    # 삭제 확인
    test_session.expire_all()
    with pytest.raises(TimerNotFoundError):
        service.get_timer(timer_id)


def test_get_timers_by_schedule(test_session, sample_schedule, test_user):
    """일정의 모든 타이머 조회 테스트"""
    service = TimerService(test_session, test_user)

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


def test_get_active_timer(test_session, sample_schedule, test_user):
    """활성 타이머 조회 테스트"""
    service = TimerService(test_session, test_user)

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


def test_get_active_timer_none(test_session, sample_schedule, test_user):
    """활성 타이머가 없을 때 None 반환 테스트"""
    service = TimerService(test_session, test_user)

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


# ============================================================
# Todo-Timer 연동 테스트
# ============================================================

def test_create_timer_with_todo_success(test_session, sample_todo, test_user):
    """Todo에 연결된 타이머 생성 성공 테스트"""
    timer_data = TimerCreate(
        todo_id=sample_todo.id,
        title="Todo 작업",
        description="Todo 관련 작업",
        allocated_duration=1800,  # 30분
    )

    service = TimerService(test_session, test_user)
    timer = service.create_timer(timer_data)

    assert timer.title == "Todo 작업"
    assert timer.description == "Todo 관련 작업"
    assert timer.allocated_duration == 1800
    assert timer.elapsed_time == 0
    assert timer.status == TimerStatus.RUNNING.value
    assert timer.started_at is not None
    assert timer.todo_id == sample_todo.id
    assert timer.schedule_id is None  # Schedule 연결 없음
    assert isinstance(timer.id, UUID)


def test_create_timer_with_both_schedule_and_todo(test_session, sample_schedule, sample_todo, test_user):
    """Schedule과 Todo 모두에 연결된 타이머 생성 성공 테스트"""
    timer_data = TimerCreate(
        schedule_id=sample_schedule.id,
        todo_id=sample_todo.id,
        title="복합 타이머",
        allocated_duration=3600,  # 1시간
    )

    service = TimerService(test_session, test_user)
    timer = service.create_timer(timer_data)

    assert timer.schedule_id == sample_schedule.id
    assert timer.todo_id == sample_todo.id
    assert timer.status == TimerStatus.RUNNING.value


def test_create_independent_timer(test_session, test_user):
    """독립 타이머 생성 성공 테스트 (Schedule, Todo 모두 없음)"""
    timer_data = TimerCreate(
        title="독립 타이머",
        description="연결 없는 독립 타이머",
        allocated_duration=600,  # 10분
    )

    service = TimerService(test_session, test_user)
    timer = service.create_timer(timer_data)

    assert timer.title == "독립 타이머"
    assert timer.schedule_id is None
    assert timer.todo_id is None
    assert timer.status == TimerStatus.RUNNING.value


def test_create_timer_invalid_todo_id(test_session, test_user):
    """존재하지 않는 Todo ID로 타이머 생성 실패 테스트"""
    from uuid import uuid4

    timer_data = TimerCreate(
        todo_id=uuid4(),
        allocated_duration=1800,
    )

    service = TimerService(test_session, test_user)
    with pytest.raises(TodoNotFoundError):
        service.create_timer(timer_data)


def test_get_timers_by_todo(test_session, sample_todo, test_user):
    """Todo의 모든 타이머 조회 테스트"""
    service = TimerService(test_session, test_user)

    # 여러 타이머 생성
    timer1_data = TimerCreate(
        todo_id=sample_todo.id,
        title="타이머 1",
        allocated_duration=1800,
    )
    timer2_data = TimerCreate(
        todo_id=sample_todo.id,
        title="타이머 2",
        allocated_duration=3600,
    )

    timer1 = service.create_timer(timer1_data)
    timer2 = service.create_timer(timer2_data)

    # Todo의 모든 타이머 조회
    timers = service.get_timers_by_todo(sample_todo.id)

    timer_ids = [t.id for t in timers]
    assert timer1.id in timer_ids
    assert timer2.id in timer_ids
    assert len(timers) >= 2


def test_get_active_timer_by_todo(test_session, sample_todo, test_user):
    """Todo의 활성 타이머 조회 테스트"""
    service = TimerService(test_session, test_user)

    # 타이머 생성 (RUNNING 상태)
    timer_data = TimerCreate(
        todo_id=sample_todo.id,
        allocated_duration=1800,
    )
    active_timer = service.create_timer(timer_data)

    # 활성 타이머 조회
    retrieved_active = service.get_active_timer_by_todo(sample_todo.id)

    assert retrieved_active is not None
    assert retrieved_active.id == active_timer.id
    assert retrieved_active.status in [TimerStatus.RUNNING.value, TimerStatus.PAUSED.value]


def test_get_active_timer_by_todo_none(test_session, sample_todo, test_user):
    """Todo의 활성 타이머가 없을 때 None 반환 테스트"""
    service = TimerService(test_session, test_user)

    # 타이머 생성 후 종료
    timer_data = TimerCreate(
        todo_id=sample_todo.id,
        allocated_duration=1800,
    )
    timer = service.create_timer(timer_data)
    service.stop_timer(timer.id)
    test_session.flush()

    # 활성 타이머 조회 (None 반환)
    active_timer = service.get_active_timer_by_todo(sample_todo.id)
    assert active_timer is None


# ============================================================
# 자동 연결 테스트
# ============================================================

def test_auto_link_schedule_to_todo(test_session, schedule_with_source_todo, todo_with_schedule, test_user):
    """Schedule만 지정 시 연관된 Todo 자동 연결 테스트"""
    service = TimerService(test_session, test_user)

    # Schedule만 지정하여 타이머 생성
    timer_data = TimerCreate(
        schedule_id=schedule_with_source_todo.id,
        allocated_duration=1800,
    )
    timer = service.create_timer(timer_data)

    # Schedule의 source_todo_id가 자동으로 연결되어야 함
    assert timer.schedule_id == schedule_with_source_todo.id
    assert timer.todo_id == todo_with_schedule.id  # 자동 연결됨!

    # 양쪽 엔드포인트에서 모두 조회 가능해야 함
    timers_by_schedule = service.get_timers_by_schedule(schedule_with_source_todo.id)
    timers_by_todo = service.get_timers_by_todo(todo_with_schedule.id)

    assert timer.id in [t.id for t in timers_by_schedule]
    assert timer.id in [t.id for t in timers_by_todo]


def test_auto_link_todo_to_schedule(test_session, todo_with_schedule, test_user):
    """Todo만 지정 시 연관된 Schedule 자동 연결 테스트"""
    service = TimerService(test_session, test_user)

    # Todo의 연관 Schedule 확인
    test_session.refresh(todo_with_schedule)
    assert len(todo_with_schedule.schedules) > 0
    linked_schedule = todo_with_schedule.schedules[0]

    # Todo만 지정하여 타이머 생성
    timer_data = TimerCreate(
        todo_id=todo_with_schedule.id,
        allocated_duration=1800,
    )
    timer = service.create_timer(timer_data)

    # Todo의 첫 번째 연관 Schedule이 자동으로 연결되어야 함
    assert timer.todo_id == todo_with_schedule.id
    assert timer.schedule_id == linked_schedule.id  # 자동 연결됨!

    # 양쪽 엔드포인트에서 모두 조회 가능해야 함
    timers_by_schedule = service.get_timers_by_schedule(linked_schedule.id)
    timers_by_todo = service.get_timers_by_todo(todo_with_schedule.id)

    assert timer.id in [t.id for t in timers_by_schedule]
    assert timer.id in [t.id for t in timers_by_todo]


def test_no_auto_link_for_unrelated_schedule(test_session, sample_schedule, test_user):
    """연관된 Todo가 없는 Schedule은 자동 연결되지 않음 테스트"""
    service = TimerService(test_session, test_user)

    # sample_schedule은 source_todo_id가 없음
    timer_data = TimerCreate(
        schedule_id=sample_schedule.id,
        allocated_duration=1800,
    )
    timer = service.create_timer(timer_data)

    # source_todo_id가 없으므로 todo_id도 None
    assert timer.schedule_id == sample_schedule.id
    assert timer.todo_id is None


def test_no_auto_link_for_todo_without_schedule(test_session, sample_todo, test_user):
    """연관된 Schedule이 없는 Todo는 자동 연결되지 않음 테스트"""
    service = TimerService(test_session, test_user)

    # sample_todo는 deadline이 없어서 연관 Schedule이 없음
    test_session.refresh(sample_todo)
    assert len(sample_todo.schedules) == 0

    timer_data = TimerCreate(
        todo_id=sample_todo.id,
        allocated_duration=1800,
    )
    timer = service.create_timer(timer_data)

    # 연관 Schedule이 없으므로 schedule_id도 None
    assert timer.todo_id == sample_todo.id
    assert timer.schedule_id is None


def test_explicit_link_overrides_auto_link(test_session, todo_with_schedule, sample_schedule, test_user):
    """명시적 지정이 자동 연결보다 우선 테스트"""
    service = TimerService(test_session, test_user)

    # sample_schedule(다른 Schedule)을 명시적으로 지정
    timer_data = TimerCreate(
        schedule_id=sample_schedule.id,
        todo_id=todo_with_schedule.id,
        allocated_duration=1800,
    )
    timer = service.create_timer(timer_data)

    # 명시적으로 지정한 값이 그대로 유지됨 (자동 연결 안 함)
    assert timer.schedule_id == sample_schedule.id
    assert timer.todo_id == todo_with_schedule.id


# ============================================================
# 타이머 목록 조회 테스트
# ============================================================

def test_get_all_timers(test_session, sample_schedule, sample_todo, test_user):
    """사용자의 모든 타이머 조회 테스트"""
    service = TimerService(test_session, test_user)

    # 다양한 타이머 생성
    timer1 = service.create_timer(TimerCreate(
        schedule_id=sample_schedule.id,
        title="Schedule 타이머",
        allocated_duration=1800,
    ))
    timer2 = service.create_timer(TimerCreate(
        todo_id=sample_todo.id,
        title="Todo 타이머",
        allocated_duration=1800,
    ))
    timer3 = service.create_timer(TimerCreate(
        title="독립 타이머",
        allocated_duration=600,
    ))

    # 모든 타이머 조회
    timers = service.get_all_timers()

    timer_ids = [t.id for t in timers]
    assert timer1.id in timer_ids
    assert timer2.id in timer_ids
    assert timer3.id in timer_ids
    assert len(timers) >= 3


def test_get_all_timers_status_filter(test_session, sample_schedule, test_user):
    """상태 필터로 타이머 조회 테스트"""
    service = TimerService(test_session, test_user)

    # 타이머 생성
    running_timer = service.create_timer(TimerCreate(
        schedule_id=sample_schedule.id,
        title="Running",
        allocated_duration=1800,
    ))
    paused_timer = service.create_timer(TimerCreate(
        schedule_id=sample_schedule.id,
        title="Paused",
        allocated_duration=1800,
    ))
    service.pause_timer(paused_timer.id)

    completed_timer = service.create_timer(TimerCreate(
        schedule_id=sample_schedule.id,
        title="Completed",
        allocated_duration=1800,
    ))
    service.stop_timer(completed_timer.id)
    test_session.flush()

    # RUNNING 상태만 조회
    running_timers = service.get_all_timers(status=[TimerStatus.RUNNING.value])
    running_ids = [t.id for t in running_timers]
    assert running_timer.id in running_ids
    assert paused_timer.id not in running_ids
    assert completed_timer.id not in running_ids

    # PAUSED 상태만 조회
    paused_timers = service.get_all_timers(status=[TimerStatus.PAUSED.value])
    paused_ids = [t.id for t in paused_timers]
    assert paused_timer.id in paused_ids

    # RUNNING + PAUSED 조회
    active_timers = service.get_all_timers(status=[
        TimerStatus.RUNNING.value,
        TimerStatus.PAUSED.value
    ])
    active_ids = [t.id for t in active_timers]
    assert running_timer.id in active_ids
    assert paused_timer.id in active_ids


def test_get_all_timers_type_filter_independent(test_session, sample_schedule, test_user):
    """독립 타이머 타입 필터 테스트"""
    service = TimerService(test_session, test_user)

    # 독립 타이머 생성
    independent_timer = service.create_timer(TimerCreate(
        title="독립 타이머",
        allocated_duration=600,
    ))
    # Schedule 연결 타이머 생성
    linked_timer = service.create_timer(TimerCreate(
        schedule_id=sample_schedule.id,
        title="연결 타이머",
        allocated_duration=1800,
    ))

    # 독립 타이머만 조회
    timers = service.get_all_timers(timer_type="independent")
    timer_ids = [t.id for t in timers]

    assert independent_timer.id in timer_ids
    assert linked_timer.id not in timer_ids


def test_get_all_timers_type_filter_schedule(test_session, sample_schedule, sample_todo, test_user):
    """Schedule 연결 타이머 타입 필터 테스트"""
    service = TimerService(test_session, test_user)

    # Schedule 연결 타이머 생성
    schedule_timer = service.create_timer(TimerCreate(
        schedule_id=sample_schedule.id,
        title="Schedule 타이머",
        allocated_duration=1800,
    ))
    # Todo 연결 타이머 생성
    todo_timer = service.create_timer(TimerCreate(
        todo_id=sample_todo.id,
        title="Todo 타이머",
        allocated_duration=1800,
    ))
    # 독립 타이머 생성
    independent_timer = service.create_timer(TimerCreate(
        title="독립 타이머",
        allocated_duration=600,
    ))

    # Schedule 연결 타이머만 조회
    timers = service.get_all_timers(timer_type="schedule")
    timer_ids = [t.id for t in timers]

    assert schedule_timer.id in timer_ids
    assert todo_timer.id not in timer_ids
    assert independent_timer.id not in timer_ids


def test_get_all_timers_type_filter_todo(test_session, sample_schedule, sample_todo, test_user):
    """Todo 연결 타이머 타입 필터 테스트"""
    service = TimerService(test_session, test_user)

    # Todo 연결 타이머 생성
    todo_timer = service.create_timer(TimerCreate(
        todo_id=sample_todo.id,
        title="Todo 타이머",
        allocated_duration=1800,
    ))
    # Schedule 연결 타이머 생성
    schedule_timer = service.create_timer(TimerCreate(
        schedule_id=sample_schedule.id,
        title="Schedule 타이머",
        allocated_duration=1800,
    ))

    # Todo 연결 타이머만 조회
    timers = service.get_all_timers(timer_type="todo")
    timer_ids = [t.id for t in timers]

    assert todo_timer.id in timer_ids
    assert schedule_timer.id not in timer_ids


def test_get_user_active_timer(test_session, sample_schedule, test_user):
    """사용자의 활성 타이머 조회 테스트"""
    service = TimerService(test_session, test_user)

    # 활성 타이머 생성 (RUNNING 상태)
    active_timer = service.create_timer(TimerCreate(
        schedule_id=sample_schedule.id,
        title="활성 타이머",
        allocated_duration=1800,
    ))

    # 활성 타이머 조회
    retrieved = service.get_user_active_timer()

    assert retrieved is not None
    assert retrieved.id == active_timer.id
    assert retrieved.status == TimerStatus.RUNNING.value


def test_get_user_active_timer_paused(test_session, sample_schedule, test_user):
    """일시정지된 타이머도 활성 타이머로 조회 테스트"""
    service = TimerService(test_session, test_user)

    # 타이머 생성 후 일시정지
    timer = service.create_timer(TimerCreate(
        schedule_id=sample_schedule.id,
        title="타이머",
        allocated_duration=1800,
    ))
    service.pause_timer(timer.id)
    test_session.flush()

    # 활성 타이머 조회 (PAUSED도 활성 타이머)
    retrieved = service.get_user_active_timer()

    assert retrieved is not None
    assert retrieved.id == timer.id
    assert retrieved.status == TimerStatus.PAUSED.value


def test_get_user_active_timer_none(test_session, sample_schedule, test_user):
    """활성 타이머가 없을 때 None 반환 테스트"""
    service = TimerService(test_session, test_user)

    # 타이머 생성 후 종료
    timer = service.create_timer(TimerCreate(
        schedule_id=sample_schedule.id,
        allocated_duration=1800,
    ))
    service.stop_timer(timer.id)
    test_session.flush()

    # 활성 타이머 조회 (None 반환)
    retrieved = service.get_user_active_timer()
    assert retrieved is None


def test_get_user_active_timer_returns_most_recent(test_session, sample_schedule, test_user):
    """여러 활성 타이머가 있을 때 가장 최근 것 반환 테스트"""
    service = TimerService(test_session, test_user)

    # 여러 타이머 생성
    timer1 = service.create_timer(TimerCreate(
        schedule_id=sample_schedule.id,
        title="첫 번째",
        allocated_duration=1800,
    ))
    timer2 = service.create_timer(TimerCreate(
        schedule_id=sample_schedule.id,
        title="두 번째 (최신)",
        allocated_duration=1800,
    ))

    # 활성 타이머 조회 (가장 최근 것 반환)
    retrieved = service.get_user_active_timer()

    assert retrieved is not None
    assert retrieved.id == timer2.id
    assert retrieved.title == "두 번째 (최신)"


# ============================================================
# 타이머 연결 변경 테스트 (todo_id, schedule_id 업데이트)
# ============================================================

def test_update_timer_add_todo_id(test_session, sample_timer, sample_todo, test_user):
    """독립 타이머에 todo_id 추가 테스트"""
    service = TimerService(test_session, test_user)

    # 초기 상태 확인
    assert sample_timer.todo_id is None

    # todo_id 추가
    update_data = TimerUpdate(todo_id=sample_todo.id)
    updated_timer = service.update_timer(sample_timer.id, update_data)

    assert updated_timer.todo_id == sample_todo.id
    # 다른 필드는 유지
    assert updated_timer.title == sample_timer.title
    assert updated_timer.schedule_id == sample_timer.schedule_id


def test_update_timer_add_schedule_id(test_session, sample_todo, sample_schedule, test_user):
    """Todo 연결 타이머에 schedule_id 추가 테스트"""
    service = TimerService(test_session, test_user)

    # Todo만 연결된 타이머 생성
    timer = service.create_timer(TimerCreate(
        todo_id=sample_todo.id,
        title="Todo 타이머",
        allocated_duration=1800,
    ))

    # schedule_id 추가
    update_data = TimerUpdate(schedule_id=sample_schedule.id)
    updated_timer = service.update_timer(timer.id, update_data)

    assert updated_timer.schedule_id == sample_schedule.id
    assert updated_timer.todo_id == sample_todo.id  # 기존 todo_id 유지


def test_update_timer_change_todo_id(test_session, sample_timer, sample_todo, test_user):
    """기존 타이머의 todo_id 변경 테스트"""
    service = TimerService(test_session, test_user)

    # sample_timer에는 schedule_id가 있음
    original_schedule_id = sample_timer.schedule_id

    # todo_id 변경
    update_data = TimerUpdate(todo_id=sample_todo.id)
    updated_timer = service.update_timer(sample_timer.id, update_data)

    assert updated_timer.todo_id == sample_todo.id
    # schedule_id는 변경하지 않았으므로 유지
    assert updated_timer.schedule_id == original_schedule_id


def test_update_timer_remove_todo_id(test_session, sample_todo, test_user):
    """타이머에서 todo_id 연결 해제 테스트"""
    service = TimerService(test_session, test_user)

    # Todo 연결된 타이머 생성
    timer = service.create_timer(TimerCreate(
        todo_id=sample_todo.id,
        title="Todo 타이머",
        allocated_duration=1800,
    ))
    assert timer.todo_id == sample_todo.id

    # todo_id를 null로 설정하여 연결 해제
    update_data = TimerUpdate(todo_id=None)
    updated_timer = service.update_timer(timer.id, update_data)

    assert updated_timer.todo_id is None


def test_update_timer_remove_schedule_id(test_session, sample_timer, test_user):
    """타이머에서 schedule_id 연결 해제 테스트"""
    service = TimerService(test_session, test_user)

    # 초기 상태: schedule_id가 있음
    assert sample_timer.schedule_id is not None

    # schedule_id를 null로 설정하여 연결 해제
    update_data = TimerUpdate(schedule_id=None)
    updated_timer = service.update_timer(sample_timer.id, update_data)

    assert updated_timer.schedule_id is None


def test_update_timer_change_both_ids(test_session, sample_timer, sample_todo, sample_schedule, test_user):
    """todo_id와 schedule_id 동시 변경 테스트"""
    service = TimerService(test_session, test_user)

    # todo_id와 schedule_id 동시 변경
    update_data = TimerUpdate(
        todo_id=sample_todo.id,
        schedule_id=sample_schedule.id,
    )
    updated_timer = service.update_timer(sample_timer.id, update_data)

    assert updated_timer.todo_id == sample_todo.id
    assert updated_timer.schedule_id == sample_schedule.id


def test_update_timer_invalid_todo_id(test_session, sample_timer, test_user):
    """존재하지 않는 todo_id로 업데이트 실패 테스트"""
    from uuid import uuid4

    service = TimerService(test_session, test_user)

    update_data = TimerUpdate(todo_id=uuid4())

    with pytest.raises(TodoNotFoundError):
        service.update_timer(sample_timer.id, update_data)


def test_update_timer_invalid_schedule_id(test_session, sample_timer, test_user):
    """존재하지 않는 schedule_id로 업데이트 실패 테스트"""
    from uuid import uuid4

    service = TimerService(test_session, test_user)

    update_data = TimerUpdate(schedule_id=uuid4())

    with pytest.raises(ScheduleNotFoundError):
        service.update_timer(sample_timer.id, update_data)


def test_update_timer_no_auto_link(test_session, todo_with_schedule, test_user):
    """업데이트 시 자동 연결이 적용되지 않는지 테스트"""
    service = TimerService(test_session, test_user)

    # 독립 타이머 생성
    timer = service.create_timer(TimerCreate(
        title="독립 타이머",
        allocated_duration=1800,
    ))
    assert timer.todo_id is None
    assert timer.schedule_id is None

    # todo_id만 추가 (자동 연결이 적용되면 schedule_id도 설정됨)
    update_data = TimerUpdate(todo_id=todo_with_schedule.id)
    updated_timer = service.update_timer(timer.id, update_data)

    # 자동 연결이 적용되지 않음: schedule_id는 여전히 None
    assert updated_timer.todo_id == todo_with_schedule.id
    assert updated_timer.schedule_id is None  # 자동 연결 안 됨!


def test_update_timer_completed_status(test_session, sample_schedule, sample_todo, test_user):
    """완료된 타이머의 연결 변경 테스트 (모든 상태에서 수정 허용)"""
    service = TimerService(test_session, test_user)

    # 타이머 생성 후 완료
    timer = service.create_timer(TimerCreate(
        schedule_id=sample_schedule.id,
        title="완료된 타이머",
        allocated_duration=1800,
    ))
    service.stop_timer(timer.id)
    test_session.flush()

    # 완료된 상태에서도 todo_id 변경 가능
    update_data = TimerUpdate(todo_id=sample_todo.id)
    updated_timer = service.update_timer(timer.id, update_data)

    assert updated_timer.todo_id == sample_todo.id
    assert updated_timer.status == TimerStatus.COMPLETED.value


def test_update_timer_preserves_unset_fields(test_session, sample_schedule, sample_todo, test_user):
    """요청에 포함되지 않은 필드는 기존 값 유지 테스트"""
    service = TimerService(test_session, test_user)

    # 타이머 생성 (schedule_id, todo_id 둘 다 설정)
    timer = service.create_timer(TimerCreate(
        schedule_id=sample_schedule.id,
        todo_id=sample_todo.id,
        title="기존 제목",
        description="기존 설명",
        allocated_duration=1800,
    ))

    # title만 업데이트 (다른 필드는 포함하지 않음)
    update_data = TimerUpdate(title="새 제목")
    updated_timer = service.update_timer(timer.id, update_data)

    # title만 변경되고 나머지는 유지
    assert updated_timer.title == "새 제목"
    assert updated_timer.description == "기존 설명"
    assert updated_timer.schedule_id == sample_schedule.id
    assert updated_timer.todo_id == sample_todo.id
