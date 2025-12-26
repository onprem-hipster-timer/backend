import pytest
from datetime import datetime, UTC
from app.crud.schedule import (
    create_schedule,
    get_schedule,
    get_schedules,
    update_schedule,
    delete_schedule,
)
from app.schemas.schedule import ScheduleCreate, ScheduleUpdate


@pytest.mark.integration
def test_create_and_get_schedule_integration(test_session):
    """DB를 포함한 일정 생성 및 조회 통합 테스트"""
    # 1. 일정 생성
    schedule_data = ScheduleCreate(
        title="통합 테스트 일정",
        description="통합 테스트 설명",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
    )
    
    created_schedule = create_schedule(test_session, schedule_data)
    schedule_id = created_schedule.id
    
    # 2. DB에서 실제로 저장되었는지 확인
    saved_schedule = get_schedule(test_session, schedule_id)
    assert saved_schedule is not None
    assert saved_schedule.id == schedule_id
    assert saved_schedule.title == "통합 테스트 일정"
    assert saved_schedule.description == "통합 테스트 설명"


@pytest.mark.integration
def test_update_schedule_integration(test_session, sample_schedule):
    """DB를 포함한 일정 업데이트 통합 테스트"""
    schedule_id = sample_schedule.id
    
    # 1. 일정 업데이트
    update_data = ScheduleUpdate(
        title="업데이트된 제목",
        description="업데이트된 설명",
    )
    
    updated_schedule = update_schedule(test_session, sample_schedule, update_data)
    
    # 2. DB에서 실제로 업데이트되었는지 확인
    saved_schedule = get_schedule(test_session, schedule_id)
    assert saved_schedule is not None
    assert saved_schedule.title == "업데이트된 제목"
    assert saved_schedule.description == "업데이트된 설명"


@pytest.mark.integration
def test_delete_schedule_integration(test_session, sample_schedule):
    """DB를 포함한 일정 삭제 통합 테스트"""
    schedule_id = sample_schedule.id
    
    # 1. 일정 삭제
    delete_schedule(test_session, sample_schedule)
    
    # 2. DB에서 실제로 삭제되었는지 확인
    deleted_schedule = get_schedule(test_session, schedule_id)
    assert deleted_schedule is None


@pytest.mark.integration
def test_get_all_schedules_integration(test_session):
    """DB를 포함한 모든 일정 조회 통합 테스트"""
    # 1. 여러 일정 생성
    schedules_data = [
        ScheduleCreate(
            title=f"일정 {i}",
            start_time=datetime(2024, 1, 1, 10 + i, 0, 0, tzinfo=UTC),
            end_time=datetime(2024, 1, 1, 12 + i, 0, 0, tzinfo=UTC),
        )
        for i in range(3)
    ]
    
    created_ids = []
    for schedule_data in schedules_data:
        schedule = create_schedule(test_session, schedule_data)
        created_ids.append(schedule.id)
    
    # 2. 모든 일정 조회
    all_schedules = get_schedules(test_session)
    
    # 3. 생성한 일정들이 모두 포함되어 있는지 확인
    assert len(all_schedules) >= 3
    retrieved_ids = {s.id for s in all_schedules}
    for created_id in created_ids:
        assert created_id in retrieved_ids


@pytest.mark.integration
def test_schedule_workflow_integration(test_session):
    """일정 전체 워크플로우 통합 테스트"""
    # 1. 일정 생성
    schedule_data = ScheduleCreate(
        title="워크플로우 테스트",
        description="초기 설명",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
    )
    
    schedule = create_schedule(test_session, schedule_data)
    schedule_id = schedule.id
    
    # 2. 일정 조회
    retrieved = get_schedule(test_session, schedule_id)
    assert retrieved.title == "워크플로우 테스트"
    
    # 3. 일정 업데이트
    update_data = ScheduleUpdate(
        title="업데이트된 워크플로우",
        description="업데이트된 설명",
    )
    updated = update_schedule(test_session, retrieved, update_data)
    assert updated.title == "업데이트된 워크플로우"
    
    # 4. 업데이트 확인
    final_check = get_schedule(test_session, schedule_id)
    assert final_check.title == "업데이트된 워크플로우"
    
    # 5. 일정 삭제
    delete_schedule(test_session, final_check)
    
    # 6. 삭제 확인
    deleted = get_schedule(test_session, schedule_id)
    assert deleted is None

