import pytest
from datetime import datetime, UTC
from uuid import UUID
from app.domain.schedule.service import ScheduleService
from app.domain.schedule.schema.dto import ScheduleCreate, ScheduleUpdate
from app.utils.validators import validate_time_order
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
    
    service = ScheduleService(test_session)
    schedule = service.create_schedule(schedule_data)
    
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
    
    service = ScheduleService(test_session)
    # Pydantic validator가 먼저 검증하므로 ValueError 발생
    with pytest.raises(ValueError, match="end_time must be after start_time"):
        service.create_schedule(schedule_data)


def test_get_schedules(test_session, sample_schedule):
    """모든 일정 조회 테스트"""
    service = ScheduleService(test_session)
    schedules = service.get_all_schedules()
    
    assert len(schedules) >= 1
    assert any(s.id == sample_schedule.id for s in schedules)


def test_get_schedule_success(test_session, sample_schedule):
    """ID로 일정 조회 성공 테스트"""
    service = ScheduleService(test_session)
    schedule = service.get_schedule(sample_schedule.id)
    
    assert schedule is not None
    assert schedule.id == sample_schedule.id
    assert schedule.title == sample_schedule.title


def test_get_schedule_not_found(test_session):
    """존재하지 않는 일정 조회 테스트"""
    from uuid import uuid4
    from app.domain.schedule.exceptions import ScheduleNotFoundError
    
    service = ScheduleService(test_session)
    non_existent_id = uuid4()
    
    with pytest.raises(ScheduleNotFoundError):
        service.get_schedule(non_existent_id)


def test_update_schedule_success(test_session, sample_schedule):
    """일정 업데이트 성공 테스트"""
    update_data = ScheduleUpdate(
        title="업데이트된 회의",
        description="업데이트된 설명",
    )
    
    service = ScheduleService(test_session)
    updated_schedule = service.update_schedule(sample_schedule.id, update_data)
    
    assert updated_schedule.title == "업데이트된 회의"
    assert updated_schedule.description == "업데이트된 설명"
    assert updated_schedule.id == sample_schedule.id


def test_update_schedule_invalid_time(test_session, sample_schedule):
    """잘못된 시간으로 일정 업데이트 실패 테스트"""
    update_data = ScheduleUpdate(
        start_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),  # end_time < start_time
    )
    
    service = ScheduleService(test_session)
    # Pydantic validator가 먼저 검증하므로 ValueError 발생
    with pytest.raises(ValueError, match="end_time must be after start_time"):
        service.update_schedule(sample_schedule.id, update_data)


def test_delete_schedule_success(test_session, sample_schedule):
    """일정 삭제 성공 테스트"""
    from app.domain.schedule.exceptions import ScheduleNotFoundError
    
    schedule_id = sample_schedule.id
    
    service = ScheduleService(test_session)
    service.delete_schedule(schedule_id)
    
    # 삭제 후 조회하면 ScheduleNotFoundError 발생
    with pytest.raises(ScheduleNotFoundError):
        service.get_schedule(schedule_id)

