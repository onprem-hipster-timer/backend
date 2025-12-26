import pytest
from datetime import datetime, UTC
from uuid import UUID
from app.crud.schedule import (
    create_schedule,
    get_schedules,
    get_schedule,
    update_schedule,
    delete_schedule,
)
from app.schemas.schedule import ScheduleCreate, ScheduleUpdate
from app.valid.schedule import validate_time_order


class MockScheduleRepository:
    """DB 없이 테스트하기 위한 Mock"""
    
    def __init__(self):
        self.schedules = {}
        self.next_id = 1
    
    def save(self, schedule):
        schedule_id = self.next_id
        self.next_id += 1
        self.schedules[schedule_id] = schedule
        return schedule
    
    def get_by_id(self, schedule_id):
        return self.schedules.get(schedule_id)
    
    def get_all(self):
        return list(self.schedules.values())


def test_validate_time_order_success():
    """시간 검증 성공 테스트"""
    start_time = datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC)
    end_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    
    # 예외가 발생하지 않아야 함
    validate_time_order(start_time, end_time)


def test_validate_time_order_failure():
    """시간 검증 실패 테스트 (end_time <= start_time)"""
    start_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    end_time = datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC)
    
    with pytest.raises(ValueError, match="end_time must be after start_time"):
        validate_time_order(start_time, end_time)


def test_create_schedule_success(test_session):
    """일정 생성 성공 테스트"""
    schedule_data = ScheduleCreate(
        title="회의",
        description="팀 회의",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
    )
    
    schedule = create_schedule(test_session, schedule_data)
    
    assert schedule.title == "회의"
    assert schedule.description == "팀 회의"
    assert schedule.start_time == schedule_data.start_time
    assert schedule.end_time == schedule_data.end_time
    assert isinstance(schedule.id, UUID)
    assert schedule.created_at is not None


def test_create_schedule_invalid_time(test_session):
    """잘못된 시간으로 일정 생성 실패 테스트"""
    schedule_data = ScheduleCreate(
        title="회의",
        start_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),  # end_time < start_time
    )
    
    with pytest.raises(ValueError, match="end_time must be after start_time"):
        create_schedule(test_session, schedule_data)


def test_get_schedules(test_session, sample_schedule):
    """모든 일정 조회 테스트"""
    schedules = get_schedules(test_session)
    
    assert len(schedules) >= 1
    assert any(s.id == sample_schedule.id for s in schedules)


def test_get_schedule_success(test_session, sample_schedule):
    """ID로 일정 조회 성공 테스트"""
    schedule = get_schedule(test_session, sample_schedule.id)
    
    assert schedule is not None
    assert schedule.id == sample_schedule.id
    assert schedule.title == sample_schedule.title


def test_get_schedule_not_found(test_session):
    """존재하지 않는 일정 조회 테스트"""
    from uuid import uuid4
    
    non_existent_id = uuid4()
    schedule = get_schedule(test_session, non_existent_id)
    
    assert schedule is None


def test_update_schedule_success(test_session, sample_schedule):
    """일정 업데이트 성공 테스트"""
    update_data = ScheduleUpdate(
        title="업데이트된 회의",
        description="업데이트된 설명",
    )
    
    updated_schedule = update_schedule(test_session, sample_schedule, update_data)
    
    assert updated_schedule.title == "업데이트된 회의"
    assert updated_schedule.description == "업데이트된 설명"
    assert updated_schedule.id == sample_schedule.id


def test_update_schedule_invalid_time(test_session, sample_schedule):
    """잘못된 시간으로 일정 업데이트 실패 테스트"""
    update_data = ScheduleUpdate(
        start_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),  # end_time < start_time
    )
    
    with pytest.raises(ValueError, match="end_time must be after start_time"):
        update_schedule(test_session, sample_schedule, update_data)


def test_delete_schedule_success(test_session, sample_schedule):
    """일정 삭제 성공 테스트"""
    schedule_id = sample_schedule.id
    
    delete_schedule(test_session, sample_schedule)
    
    # 삭제 후 조회하면 None이어야 함
    deleted_schedule = get_schedule(test_session, schedule_id)
    assert deleted_schedule is None

