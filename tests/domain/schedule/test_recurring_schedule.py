"""
반복 일정 관련 테스트

RRULE 기반 반복 일정의 생성, 조회, 수정, 삭제를 테스트합니다.
"""
from datetime import datetime, UTC
from uuid import uuid4

import pytest

from app.domain.schedule.exceptions import (
    InvalidRecurrenceRuleError,
    InvalidRecurrenceEndError,
    RecurringScheduleError,
    ScheduleNotFoundError,
)
from app.domain.schedule.schema.dto import ScheduleCreate, ScheduleUpdate
from app.domain.schedule.service import ScheduleService
from app.models.schedule import ScheduleException


# ==================== 반복 일정 생성 테스트 ====================

def test_create_recurring_schedule_weekly(test_session, test_user):
    """주간 반복 일정 생성 테스트"""
    schedule_data = ScheduleCreate(
        title="주간 회의",
        description="매주 월요일 회의",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),  # 2024-01-01은 월요일
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        recurrence_rule="FREQ=WEEKLY;BYDAY=MO",
    )

    service = ScheduleService(test_session, test_user)
    schedule = service.create_schedule(schedule_data)

    assert schedule.title == "주간 회의"
    assert schedule.recurrence_rule == "FREQ=WEEKLY;BYDAY=MO"
    assert schedule.recurrence_end is None  # 무한 반복
    assert schedule.parent_id is None


def test_create_recurring_schedule_with_end_date(test_session, test_user):
    """종료일이 있는 반복 일정 생성 테스트"""
    schedule_data = ScheduleCreate(
        title="한 달 회의",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        recurrence_rule="FREQ=WEEKLY;BYDAY=MO",
        recurrence_end=datetime(2024, 1, 31, 23, 59, 59, tzinfo=UTC),
    )

    service = ScheduleService(test_session, test_user)
    schedule = service.create_schedule(schedule_data)

    assert schedule.recurrence_rule == "FREQ=WEEKLY;BYDAY=MO"
    assert schedule.recurrence_end == datetime(2024, 1, 31, 23, 59, 59)


def test_create_recurring_schedule_invalid_rrule(test_session, test_user):
    """잘못된 RRULE로 반복 일정 생성 실패 테스트"""
    schedule_data = ScheduleCreate(
        title="잘못된 반복 일정",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        recurrence_rule="INVALID_RRULE",
    )

    service = ScheduleService(test_session, test_user)
    with pytest.raises(InvalidRecurrenceRuleError):
        service.create_schedule(schedule_data)


def test_create_recurring_schedule_invalid_end_date(test_session, test_user):
    """종료일이 시작일 이전인 반복 일정 생성 실패 테스트"""
    schedule_data = ScheduleCreate(
        title="잘못된 종료일",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        recurrence_rule="FREQ=WEEKLY;BYDAY=MO",
        recurrence_end=datetime(2023, 12, 31, 23, 59, 59, tzinfo=UTC),  # 시작일 이전
    )

    service = ScheduleService(test_session, test_user)
    with pytest.raises(InvalidRecurrenceEndError):
        service.create_schedule(schedule_data)


# ==================== 반복 일정 조회 테스트 ====================

def test_get_recurring_schedules_expands_instances(test_session, test_user):
    """반복 일정 조회 시 가상 인스턴스 확장 테스트"""
    # 주간 반복 일정 생성 (매주 월요일)
    schedule_data = ScheduleCreate(
        title="주간 회의",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),  # 2024-01-01은 월요일
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        recurrence_rule="FREQ=WEEKLY;BYDAY=MO",
        recurrence_end=datetime(2024, 1, 29, 23, 59, 59, tzinfo=UTC),  # 4주간
    )

    service = ScheduleService(test_session, test_user)
    parent_schedule = service.create_schedule(schedule_data)

    # 1월 전체 조회 (5개의 월요일이 있어야 함)
    start_date = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
    end_date = datetime(2024, 1, 31, 23, 59, 59, tzinfo=UTC)

    schedules = service.get_schedules_by_date_range(start_date, end_date)

    # 가상 인스턴스들이 확장되어야 함
    recurring_instances = [s for s in schedules if s.parent_id == parent_schedule.id]
    assert len(recurring_instances) == 5  # 1월의 5개 월요일

    # 각 인스턴스가 고유 ID를 가져야 함
    instance_ids = {s.id for s in recurring_instances}
    assert len(instance_ids) == 5  # 모두 다른 ID

    # 각 인스턴스의 시작 시간이 월요일이어야 함
    for instance in recurring_instances:
        assert instance.start_time.weekday() == 0  # 월요일
        assert instance.parent_id == parent_schedule.id
        assert instance.recurrence_rule is None  # 가상 인스턴스는 반복 규칙 없음


def test_get_recurring_schedules_filters_by_date_range(test_session, test_user):
    """반복 일정 조회 시 날짜 범위 필터링 테스트"""
    schedule_data = ScheduleCreate(
        title="일일 회의",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        recurrence_rule="FREQ=DAILY",
        recurrence_end=datetime(2024, 1, 10, 23, 59, 59, tzinfo=UTC),
    )

    service = ScheduleService(test_session, test_user)
    parent_schedule = service.create_schedule(schedule_data)

    # 1월 5일부터 7일까지만 조회
    start_date = datetime(2024, 1, 5, 0, 0, 0, tzinfo=UTC)
    end_date = datetime(2024, 1, 7, 23, 59, 59, tzinfo=UTC)

    schedules = service.get_schedules_by_date_range(start_date, end_date)

    recurring_instances = [s for s in schedules if s.parent_id == parent_schedule.id]
    assert len(recurring_instances) == 3  # 5일, 6일, 7일

    # 각 인스턴스의 날짜 확인
    dates = {s.start_time.date() for s in recurring_instances}
    assert dates == {datetime(2024, 1, 5).date(), datetime(2024, 1, 6).date(), datetime(2024, 1, 7).date()}


def test_get_recurring_schedules_mixed_with_regular(test_session, test_user):
    """반복 일정과 일반 일정이 함께 조회되는지 테스트"""
    # 일반 일정
    regular_data = ScheduleCreate(
        title="일반 일정",
        start_time=datetime(2024, 1, 5, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 5, 12, 0, 0, tzinfo=UTC),
    )

    # 반복 일정
    recurring_data = ScheduleCreate(
        title="반복 일정",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        recurrence_rule="FREQ=DAILY",
        recurrence_end=datetime(2024, 1, 10, 23, 59, 59, tzinfo=UTC),
    )

    service = ScheduleService(test_session, test_user)
    regular_schedule = service.create_schedule(regular_data)
    recurring_schedule = service.create_schedule(recurring_data)

    # 1월 5일 조회
    start_date = datetime(2024, 1, 5, 0, 0, 0, tzinfo=UTC)
    end_date = datetime(2024, 1, 5, 23, 59, 59, tzinfo=UTC)

    schedules = service.get_schedules_by_date_range(start_date, end_date)

    # 일반 일정 1개 + 반복 일정 인스턴스 1개
    regular_schedules = [s for s in schedules if s.id == regular_schedule.id]
    recurring_instances = [s for s in schedules if s.parent_id == recurring_schedule.id]

    assert len(regular_schedules) == 1
    assert len(recurring_instances) == 1


# ==================== 반복 일정 인스턴스 수정 테스트 ====================

def test_update_recurring_instance(test_session, test_user):
    """반복 일정의 특정 인스턴스 수정 테스트"""
    # 주간 반복 일정 생성
    schedule_data = ScheduleCreate(
        title="주간 회의",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),  # 월요일
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        recurrence_rule="FREQ=WEEKLY;BYDAY=MO",
    )

    service = ScheduleService(test_session, test_user)
    parent_schedule = service.create_schedule(schedule_data)

    # 첫 번째 인스턴스(2024-01-01) 수정
    instance_start = datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC)
    update_data = ScheduleUpdate(
        title="수정된 회의",
        description="특별 회의",
    )

    updated_instance = service.update_recurring_instance(
        parent_schedule.id,
        instance_start,
        update_data
    )

    # 가상 인스턴스 반환 확인
    assert updated_instance.title == "수정된 회의"
    assert updated_instance.description == "특별 회의"
    assert updated_instance.parent_id == parent_schedule.id
    assert updated_instance.start_time == datetime(2024, 1, 1, 10, 0, 0)

    # ScheduleException이 생성되었는지 확인
    from app.crud import schedule as crud
    exception = crud.get_schedule_exception_by_date(
        test_session,
        parent_schedule.id,
        datetime(2024, 1, 1, 10, 0, 0),
        test_user.sub,
    )
    assert exception is not None
    assert exception.title == "수정된 회의"
    assert exception.is_deleted is False

    # 조회 시 수정된 인스턴스가 반영되는지 확인
    start_date = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
    end_date = datetime(2024, 1, 1, 23, 59, 59, tzinfo=UTC)
    schedules = service.get_schedules_by_date_range(start_date, end_date)

    modified_instance = next(
        (s for s in schedules if
         s.parent_id == parent_schedule.id and s.start_time.date() == datetime(2024, 1, 1).date()),
        None
    )
    assert modified_instance is not None
    assert modified_instance.title == "수정된 회의"


def test_update_recurring_instance_not_recurring(test_session, sample_schedule, test_user):
    """반복 일정이 아닌 일정에 대해 인스턴스 수정 시도 실패 테스트"""
    service = ScheduleService(test_session, test_user)
    update_data = ScheduleUpdate(title="수정")

    with pytest.raises(RecurringScheduleError):
        service.update_recurring_instance(
            sample_schedule.id,
            datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
            update_data
        )


def test_update_recurring_instance_parent_not_found(test_session, test_user):
    """존재하지 않는 부모 일정에 대해 인스턴스 수정 시도 실패 테스트"""
    service = ScheduleService(test_session, test_user)
    update_data = ScheduleUpdate(title="수정")
    non_existent_id = uuid4()

    with pytest.raises(ScheduleNotFoundError):
        service.update_recurring_instance(
            non_existent_id,
            datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
            update_data
        )


# ==================== 반복 일정 인스턴스 삭제 테스트 ====================

def test_delete_recurring_instance(test_session, test_user):
    """반복 일정의 특정 인스턴스 삭제 테스트"""
    # 주간 반복 일정 생성
    schedule_data = ScheduleCreate(
        title="주간 회의",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),  # 월요일
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        recurrence_rule="FREQ=WEEKLY;BYDAY=MO",
        recurrence_end=datetime(2024, 1, 29, 23, 59, 59, tzinfo=UTC),  # 4주간
    )

    service = ScheduleService(test_session, test_user)
    parent_schedule = service.create_schedule(schedule_data)

    # 첫 번째 인스턴스(2024-01-01) 삭제
    instance_start = datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC)
    service.delete_recurring_instance(parent_schedule.id, instance_start)

    # ScheduleException이 생성되었는지 확인
    from app.crud import schedule as crud
    exception = crud.get_schedule_exception_by_date(
        test_session,
        parent_schedule.id,
        datetime(2024, 1, 1, 10, 0, 0),
        test_user.sub,
    )
    assert exception is not None
    assert exception.is_deleted is True

    # 조회 시 삭제된 인스턴스가 제외되는지 확인
    start_date = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
    end_date = datetime(2024, 1, 31, 23, 59, 59, tzinfo=UTC)
    schedules = service.get_schedules_by_date_range(start_date, end_date)

    recurring_instances = [s for s in schedules if s.parent_id == parent_schedule.id]
    assert len(recurring_instances) == 4  # 1월 1일 제외하고 4개만 남음

    # 삭제된 인스턴스가 없는지 확인
    deleted_instance = next(
        (s for s in recurring_instances if s.start_time.date() == datetime(2024, 1, 1).date()),
        None
    )
    assert deleted_instance is None


def test_delete_recurring_instance_not_recurring(test_session, sample_schedule, test_user):
    """반복 일정이 아닌 일정에 대해 인스턴스 삭제 시도 실패 테스트"""
    service = ScheduleService(test_session, test_user)

    with pytest.raises(RecurringScheduleError):
        service.delete_recurring_instance(
            sample_schedule.id,
            datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC)
        )


# ==================== CASCADE DELETE 테스트 ====================

def test_delete_recurring_schedule_cascade_delete(test_engine, test_user):
    """반복 일정 삭제 시 관련 예외 인스턴스 CASCADE DELETE 테스트"""
    from sqlmodel import Session
    from app.domain.schedule.service import ScheduleService
    from app.domain.schedule.schema.dto import ScheduleCreate
    from app.crud import schedule as crud

    # 반복 일정 생성
    schedule_data = ScheduleCreate(
        title="주간 회의",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        recurrence_rule="FREQ=WEEKLY;BYDAY=MO",
    )

    parent_schedule_id = None
    exception_id = None

    with Session(test_engine) as session:
        service = ScheduleService(session, test_user)
        parent_schedule = service.create_schedule(schedule_data)
        session.commit()
        parent_schedule_id = parent_schedule.id  # 세션이 열려 있을 때 ID 저장

        # 예외 인스턴스 생성
        exception = crud.create_schedule_exception(
            session,
            parent_id=parent_schedule.id,
            exception_date=datetime(2024, 1, 1, 10, 0, 0),
            owner_id=test_user.sub,
            is_deleted=False,
            title="수정된 회의",
        )
        session.commit()
        exception_id = exception.id  # 세션이 열려 있을 때 ID 저장

    # 부모 일정 삭제
    with Session(test_engine) as delete_session:
        delete_service = ScheduleService(delete_session, test_user)
        delete_service.delete_schedule(parent_schedule_id)  # 저장된 ID 사용
        delete_session.commit()

    # 예외 인스턴스가 자동으로 삭제되었는지 확인
    with Session(test_engine) as check_session:
        from sqlmodel import select
        statement = select(ScheduleException).where(ScheduleException.id == exception_id)
        result = check_session.exec(statement).first()
        assert result is None  # CASCADE DELETE로 삭제됨


def test_delete_all_instances_deletes_parent_schedule(test_engine, test_user):
    """모든 인스턴스 삭제 시 부모 일정도 자동 삭제되는지 테스트"""
    from sqlmodel import Session
    from app.domain.schedule.service import ScheduleService
    from app.domain.schedule.schema.dto import ScheduleCreate
    from app.models.schedule import Schedule

    # 반복 일정 생성 (4주간 주간 반복 - 4개의 월요일)
    schedule_data = ScheduleCreate(
        title="주간 회의",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),  # 2024-01-01은 월요일
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        recurrence_rule="FREQ=WEEKLY;BYDAY=MO",
        recurrence_end=datetime(2024, 1, 29, 23, 59, 59, tzinfo=UTC),  # 4주간
    )

    parent_schedule_id = None

    with Session(test_engine) as session:
        service = ScheduleService(session, test_user)
        parent_schedule = service.create_schedule(schedule_data)
        session.commit()
        parent_schedule_id = parent_schedule.id

    # 각 인스턴스를 하나씩 삭제
    instance_dates = [
        datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),  # 1월 1일 (월요일)
        datetime(2024, 1, 8, 10, 0, 0, tzinfo=UTC),  # 1월 8일 (월요일)
        datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),  # 1월 15일 (월요일)
        datetime(2024, 1, 22, 10, 0, 0, tzinfo=UTC),  # 1월 22일 (월요일)
        datetime(2024, 1, 29, 10, 0, 0, tzinfo=UTC),  # 1월 29일 (월요일)
    ]

    # 처음 4개 인스턴스 삭제 (부모 일정은 아직 남아있어야 함)
    for i, instance_date in enumerate(instance_dates[:-1]):
        with Session(test_engine) as delete_session:
            delete_service = ScheduleService(delete_session, test_user)
            delete_service.delete_recurring_instance(parent_schedule_id, instance_date)
            delete_session.commit()

        # 부모 일정이 아직 존재하는지 확인
        with Session(test_engine) as check_session:
            parent = check_session.get(Schedule, parent_schedule_id)
            assert parent is not None, f"{i + 1}번째 인스턴스 삭제 후에도 부모 일정이 존재해야 함"

    # 마지막 인스턴스 삭제 (부모 일정도 자동 삭제되어야 함)
    with Session(test_engine) as delete_session:
        delete_service = ScheduleService(delete_session, test_user)
        delete_service.delete_recurring_instance(parent_schedule_id, instance_dates[-1])
        delete_session.commit()

    # 부모 일정이 자동으로 삭제되었는지 확인
    with Session(test_engine) as check_session:
        parent = check_session.get(Schedule, parent_schedule_id)
        assert parent is None, "모든 인스턴스 삭제 시 부모 일정도 자동 삭제되어야 함"


# ==================== 예외 인스턴스 복합 시나리오 테스트 ====================

def test_recurring_schedule_with_multiple_exceptions(test_session, test_user):
    """여러 예외 인스턴스가 있는 반복 일정 조회 테스트"""
    # 주간 반복 일정 생성
    schedule_data = ScheduleCreate(
        title="주간 회의",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),  # 월요일
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        recurrence_rule="FREQ=WEEKLY;BYDAY=MO",
        recurrence_end=datetime(2024, 1, 29, 23, 59, 59, tzinfo=UTC),  # 4주간
    )

    service = ScheduleService(test_session, test_user)
    parent_schedule = service.create_schedule(schedule_data)

    # 첫 번째 인스턴스 수정
    service.update_recurring_instance(
        parent_schedule.id,
        datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
        ScheduleUpdate(title="수정된 회의 1")
    )

    # 두 번째 인스턴스 삭제
    service.delete_recurring_instance(
        parent_schedule.id,
        datetime(2024, 1, 8, 10, 0, 0, tzinfo=UTC)
    )

    # 세 번째 인스턴스 수정
    service.update_recurring_instance(
        parent_schedule.id,
        datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
        ScheduleUpdate(title="수정된 회의 3")
    )

    # 조회
    start_date = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
    end_date = datetime(2024, 1, 31, 23, 59, 59, tzinfo=UTC)
    schedules = service.get_schedules_by_date_range(start_date, end_date)

    recurring_instances = [s for s in schedules if s.parent_id == parent_schedule.id]

    # 5개 인스턴스 중 1개 삭제, 2개 수정, 2개 원본
    assert len(recurring_instances) == 4  # 삭제된 인스턴스 제외

    # 각 인스턴스 확인
    instance_by_date = {s.start_time.date(): s for s in recurring_instances}

    # 1월 1일: 수정됨
    assert instance_by_date[datetime(2024, 1, 1).date()].title == "수정된 회의 1"

    # 1월 8일: 삭제됨 (조회 결과에 없어야 함)
    assert datetime(2024, 1, 8).date() not in instance_by_date

    # 1월 15일: 수정됨
    assert instance_by_date[datetime(2024, 1, 15).date()].title == "수정된 회의 3"

    # 1월 22일: 원본
    assert instance_by_date[datetime(2024, 1, 22).date()].title == "주간 회의"


def test_update_deleted_instance_restores_it(test_session, test_user):
    """삭제된 인스턴스를 수정하면 복원되는지 테스트"""
    # 주간 반복 일정 생성
    schedule_data = ScheduleCreate(
        title="주간 회의",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        recurrence_rule="FREQ=WEEKLY;BYDAY=MO",
    )

    service = ScheduleService(test_session, test_user)
    parent_schedule = service.create_schedule(schedule_data)

    # 인스턴스 삭제
    instance_start = datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC)
    service.delete_recurring_instance(parent_schedule.id, instance_start)

    # 삭제된 인스턴스 수정 (복원)
    service.update_recurring_instance(
        parent_schedule.id,
        instance_start,
        ScheduleUpdate(title="복원된 회의")
    )

    # 조회 시 복원된 인스턴스가 나타나는지 확인
    start_date = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
    end_date = datetime(2024, 1, 1, 23, 59, 59, tzinfo=UTC)
    schedules = service.get_schedules_by_date_range(start_date, end_date)

    restored_instance = next(
        (s for s in schedules if s.parent_id == parent_schedule.id),
        None
    )
    assert restored_instance is not None
    assert restored_instance.title == "복원된 회의"


# ==================== RRULE 패턴 테스트 ====================

def test_weekly_multiple_weekdays(test_session, test_user):
    """여러 요일을 사용하는 주간 반복 테스트"""
    # 매주 화요일과 수요일 반복
    schedule_data = ScheduleCreate(
        title="주간 회의",
        start_time=datetime(2024, 1, 2, 10, 0, 0, tzinfo=UTC),  # 2024-01-02는 화요일
        end_time=datetime(2024, 1, 2, 12, 0, 0, tzinfo=UTC),
        recurrence_rule="FREQ=WEEKLY;BYDAY=TU,WE",
    )

    service = ScheduleService(test_session, test_user)
    parent_schedule = service.create_schedule(schedule_data)

    # 1월 전체 조회
    start_date = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
    end_date = datetime(2024, 1, 31, 23, 59, 59, tzinfo=UTC)
    schedules = service.get_schedules_by_date_range(start_date, end_date)

    recurring_instances = [s for s in schedules if s.parent_id == parent_schedule.id]

    # 1월에는 화요일 5개, 수요일 5개 = 총 10개
    assert len(recurring_instances) == 10

    # 각 인스턴스가 화요일 또는 수요일인지 확인
    for instance in recurring_instances:
        weekday = instance.start_time.weekday()
        assert weekday in [1, 2], f"인스턴스는 화요일(1) 또는 수요일(2)이어야 함, 실제: {weekday}"

    # 날짜 순서 확인
    dates = [s.start_time.date() for s in recurring_instances]
    assert dates == sorted(dates), "날짜가 순서대로 정렬되어야 함"


def test_weekly_multiple_weekdays_three_days(test_session, test_user):
    """3개 요일을 사용하는 주간 반복 테스트"""
    # 매주 월/수/금 반복
    schedule_data = ScheduleCreate(
        title="주간 회의",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),  # 2024-01-01은 월요일
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        recurrence_rule="FREQ=WEEKLY;BYDAY=MO,WE,FR",
        recurrence_end=datetime(2024, 1, 31, 23, 59, 59, tzinfo=UTC),
    )

    service = ScheduleService(test_session, test_user)
    parent_schedule = service.create_schedule(schedule_data)

    # 1월 전체 조회
    start_date = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
    end_date = datetime(2024, 1, 31, 23, 59, 59, tzinfo=UTC)
    schedules = service.get_schedules_by_date_range(start_date, end_date)

    recurring_instances = [s for s in schedules if s.parent_id == parent_schedule.id]

    # 1월에는 월요일 5개, 수요일 5개, 금요일 4개 = 총 14개
    assert len(recurring_instances) == 14

    # 각 인스턴스가 월/수/금인지 확인
    for instance in recurring_instances:
        weekday = instance.start_time.weekday()
        assert weekday in [0, 2, 4], f"인스턴스는 월요일(0), 수요일(2), 또는 금요일(4)이어야 함, 실제: {weekday}"


def test_weekly_with_count(test_session, test_user):
    """COUNT를 사용하는 주간 반복 테스트"""
    # 매주 월요일, 5회만 반복
    schedule_data = ScheduleCreate(
        title="주간 회의",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),  # 2024-01-01은 월요일
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        recurrence_rule="FREQ=WEEKLY;BYDAY=MO;COUNT=5",
    )

    service = ScheduleService(test_session, test_user)
    parent_schedule = service.create_schedule(schedule_data)

    # 충분한 범위로 조회
    start_date = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
    end_date = datetime(2024, 3, 31, 23, 59, 59, tzinfo=UTC)
    schedules = service.get_schedules_by_date_range(start_date, end_date)

    recurring_instances = [s for s in schedules if s.parent_id == parent_schedule.id]

    # COUNT=5이므로 정확히 5개만 생성되어야 함
    assert len(recurring_instances) == 5

    # 각 인스턴스가 월요일인지 확인
    for instance in recurring_instances:
        assert instance.start_time.weekday() == 0  # 월요일

    # 예상 날짜: 1/1, 1/8, 1/15, 1/22, 1/29
    expected_dates = [
        datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC).date(),
        datetime(2024, 1, 8, 10, 0, 0, tzinfo=UTC).date(),
        datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC).date(),
        datetime(2024, 1, 22, 10, 0, 0, tzinfo=UTC).date(),
        datetime(2024, 1, 29, 10, 0, 0, tzinfo=UTC).date(),
    ]
    actual_dates = [s.start_time.date() for s in recurring_instances]
    assert set(actual_dates) == set(expected_dates)


def test_daily_with_count(test_session, test_user):
    """COUNT를 사용하는 일일 반복 테스트"""
    # 매일, 7일간만 반복
    schedule_data = ScheduleCreate(
        title="일일 회의",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        recurrence_rule="FREQ=DAILY;COUNT=7",
    )

    service = ScheduleService(test_session, test_user)
    parent_schedule = service.create_schedule(schedule_data)

    # 충분한 범위로 조회
    start_date = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
    end_date = datetime(2024, 1, 31, 23, 59, 59, tzinfo=UTC)
    schedules = service.get_schedules_by_date_range(start_date, end_date)

    recurring_instances = [s for s in schedules if s.parent_id == parent_schedule.id]

    # COUNT=7이므로 정확히 7개만 생성되어야 함
    assert len(recurring_instances) == 7

    # 예상 날짜: 1/1 ~ 1/7
    expected_dates = [
        datetime(2024, 1, i, 10, 0, 0, tzinfo=UTC).date()
        for i in range(1, 8)
    ]
    actual_dates = [s.start_time.date() for s in recurring_instances]
    assert set(actual_dates) == set(expected_dates)


def test_weekly_count_with_multiple_days(test_session, test_user):
    """COUNT와 여러 요일을 함께 사용하는 테스트"""
    # 매주 화요일과 수요일, 총 10회 반복 (5주간)
    schedule_data = ScheduleCreate(
        title="주간 회의",
        start_time=datetime(2024, 1, 2, 10, 0, 0, tzinfo=UTC),  # 2024-01-02는 화요일
        end_time=datetime(2024, 1, 2, 12, 0, 0, tzinfo=UTC),
        recurrence_rule="FREQ=WEEKLY;BYDAY=TU,WE;COUNT=10",
    )

    service = ScheduleService(test_session, test_user)
    parent_schedule = service.create_schedule(schedule_data)

    # 충분한 범위로 조회
    start_date = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
    end_date = datetime(2024, 3, 31, 23, 59, 59, tzinfo=UTC)
    schedules = service.get_schedules_by_date_range(start_date, end_date)

    recurring_instances = [s for s in schedules if s.parent_id == parent_schedule.id]

    # COUNT=10이므로 정확히 10개만 생성되어야 함 (5주 * 2일)
    assert len(recurring_instances) == 10

    # 각 인스턴스가 화요일 또는 수요일인지 확인
    for instance in recurring_instances:
        weekday = instance.start_time.weekday()
        assert weekday in [1, 2], f"인스턴스는 화요일(1) 또는 수요일(2)이어야 함, 실제: {weekday}"


def test_weekly_with_interval(test_session, test_user):
    """INTERVAL을 사용하는 주간 반복 테스트 (격주)"""
    # 격주 월요일 반복
    schedule_data = ScheduleCreate(
        title="격주 회의",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),  # 2024-01-01은 월요일
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        recurrence_rule="FREQ=WEEKLY;INTERVAL=2;BYDAY=MO",
        recurrence_end=datetime(2024, 2, 29, 23, 59, 59, tzinfo=UTC),
    )

    service = ScheduleService(test_session, test_user)
    parent_schedule = service.create_schedule(schedule_data)

    # 1월~2월 조회
    start_date = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
    end_date = datetime(2024, 2, 29, 23, 59, 59, tzinfo=UTC)
    schedules = service.get_schedules_by_date_range(start_date, end_date)

    recurring_instances = [s for s in schedules if s.parent_id == parent_schedule.id]

    # 격주이므로 1월에는 1/1, 1/15, 1/29 = 3개, 2월에는 2/12, 2/26 = 2개, 총 5개
    assert len(recurring_instances) == 5

    # 각 인스턴스가 월요일인지 확인
    for instance in recurring_instances:
        assert instance.start_time.weekday() == 0  # 월요일

    # 예상 날짜 확인
    expected_dates = [
        datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC).date(),
        datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC).date(),
        datetime(2024, 1, 29, 10, 0, 0, tzinfo=UTC).date(),
        datetime(2024, 2, 12, 10, 0, 0, tzinfo=UTC).date(),
        datetime(2024, 2, 26, 10, 0, 0, tzinfo=UTC).date(),
    ]
    actual_dates = [s.start_time.date() for s in recurring_instances]
    assert set(actual_dates) == set(expected_dates)


def test_monthly_by_monthday(test_session, test_user):
    """월간 반복 테스트 (일자 기준)"""
    # 매월 15일 반복
    schedule_data = ScheduleCreate(
        title="월간 회의",
        start_time=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
        recurrence_rule="FREQ=MONTHLY;BYMONTHDAY=15",
        recurrence_end=datetime(2024, 6, 30, 23, 59, 59, tzinfo=UTC),
    )

    service = ScheduleService(test_session, test_user)
    parent_schedule = service.create_schedule(schedule_data)

    # 1월~6월 조회
    start_date = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
    end_date = datetime(2024, 6, 30, 23, 59, 59, tzinfo=UTC)
    schedules = service.get_schedules_by_date_range(start_date, end_date)

    recurring_instances = [s for s in schedules if s.parent_id == parent_schedule.id]

    # 6개월이므로 6개 생성되어야 함
    assert len(recurring_instances) == 6

    # 각 인스턴스가 15일인지 확인
    for instance in recurring_instances:
        assert instance.start_time.day == 15


def test_monthly_by_weekday_first(test_session, test_user):
    """월간 반복 테스트 (첫 번째 요일)"""
    # 매월 첫 번째 월요일 반복
    schedule_data = ScheduleCreate(
        title="월간 회의",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),  # 2024-01-01은 월요일
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        recurrence_rule="FREQ=MONTHLY;BYDAY=1MO",
        recurrence_end=datetime(2024, 6, 30, 23, 59, 59, tzinfo=UTC),
    )

    service = ScheduleService(test_session, test_user)
    parent_schedule = service.create_schedule(schedule_data)

    # 1월~6월 조회
    start_date = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
    end_date = datetime(2024, 6, 30, 23, 59, 59, tzinfo=UTC)
    schedules = service.get_schedules_by_date_range(start_date, end_date)

    recurring_instances = [s for s in schedules if s.parent_id == parent_schedule.id]

    # 6개월이므로 6개 생성되어야 함
    assert len(recurring_instances) == 6

    # 각 인스턴스가 첫 번째 월요일인지 확인
    for instance in recurring_instances:
        assert instance.start_time.weekday() == 0  # 월요일
        # 해당 월의 첫 번째 월요일인지 확인 (1일~7일 사이)
        assert 1 <= instance.start_time.day <= 7


def test_monthly_by_weekday_last(test_session, test_user):
    """월간 반복 테스트 (마지막 요일)"""
    # 매월 마지막 금요일 반복
    schedule_data = ScheduleCreate(
        title="월간 회의",
        start_time=datetime(2024, 1, 26, 10, 0, 0, tzinfo=UTC),  # 2024-01-26은 금요일 (마지막 금요일)
        end_time=datetime(2024, 1, 26, 12, 0, 0, tzinfo=UTC),
        recurrence_rule="FREQ=MONTHLY;BYDAY=-1FR",
        recurrence_end=datetime(2024, 6, 30, 23, 59, 59, tzinfo=UTC),
    )

    service = ScheduleService(test_session, test_user)
    parent_schedule = service.create_schedule(schedule_data)

    # 1월~6월 조회
    start_date = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
    end_date = datetime(2024, 6, 30, 23, 59, 59, tzinfo=UTC)
    schedules = service.get_schedules_by_date_range(start_date, end_date)

    recurring_instances = [s for s in schedules if s.parent_id == parent_schedule.id]

    # 6개월이므로 6개 생성되어야 함
    assert len(recurring_instances) == 6

    # 각 인스턴스가 마지막 금요일인지 확인
    for instance in recurring_instances:
        assert instance.start_time.weekday() == 4  # 금요일
        # 해당 월의 마지막 주 금요일인지 확인 (23일 이후)
        assert instance.start_time.day >= 23


def test_monthly_with_interval(test_session, test_user):
    """INTERVAL을 사용하는 월간 반복 테스트 (격월)"""
    # 3개월마다 반복
    schedule_data = ScheduleCreate(
        title="분기 회의",
        start_time=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
        recurrence_rule="FREQ=MONTHLY;INTERVAL=3;BYMONTHDAY=15",
        recurrence_end=datetime(2024, 12, 31, 23, 59, 59, tzinfo=UTC),
    )

    service = ScheduleService(test_session, test_user)
    parent_schedule = service.create_schedule(schedule_data)

    # 1월~12월 조회
    start_date = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
    end_date = datetime(2024, 12, 31, 23, 59, 59, tzinfo=UTC)
    schedules = service.get_schedules_by_date_range(start_date, end_date)

    recurring_instances = [s for s in schedules if s.parent_id == parent_schedule.id]

    # 3개월마다이므로 1월, 4월, 7월, 10월 = 4개
    assert len(recurring_instances) == 4

    # 각 인스턴스가 15일인지 확인
    for instance in recurring_instances:
        assert instance.start_time.day == 15

    # 예상 월 확인
    expected_months = [1, 4, 7, 10]
    actual_months = [s.start_time.month for s in recurring_instances]
    assert set(actual_months) == set(expected_months)


def test_yearly_by_month_and_day(test_session, test_user):
    """연간 반복 테스트 (월과 일자)"""
    # 매년 1월 1일 반복
    schedule_data = ScheduleCreate(
        title="신년 회의",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        recurrence_rule="FREQ=YEARLY;BYMONTH=1;BYMONTHDAY=1",
        recurrence_end=datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC),
    )

    service = ScheduleService(test_session, test_user)
    parent_schedule = service.create_schedule(schedule_data)

    # 2024~2026년 조회
    start_date = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
    end_date = datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC)
    schedules = service.get_schedules_by_date_range(start_date, end_date)

    recurring_instances = [s for s in schedules if s.parent_id == parent_schedule.id]

    # 3년이므로 3개 생성되어야 함
    assert len(recurring_instances) == 3

    # 각 인스턴스가 1월 1일인지 확인
    for instance in recurring_instances:
        assert instance.start_time.month == 1
        assert instance.start_time.day == 1

    # 예상 연도 확인
    expected_years = [2024, 2025, 2026]
    actual_years = [s.start_time.year for s in recurring_instances]
    assert set(actual_years) == set(expected_years)


def test_yearly_by_month_and_weekday(test_session, test_user):
    """연간 반복 테스트 (월과 요일)"""
    # 매년 12월 25일 반복 (크리스마스)
    schedule_data = ScheduleCreate(
        title="크리스마스",
        start_time=datetime(2024, 12, 25, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 12, 25, 12, 0, 0, tzinfo=UTC),
        recurrence_rule="FREQ=YEARLY;BYMONTH=12;BYMONTHDAY=25",
        recurrence_end=datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC),
    )

    service = ScheduleService(test_session, test_user)
    parent_schedule = service.create_schedule(schedule_data)

    # 2024~2026년 조회
    start_date = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
    end_date = datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC)
    schedules = service.get_schedules_by_date_range(start_date, end_date)

    recurring_instances = [s for s in schedules if s.parent_id == parent_schedule.id]

    # 3년이므로 3개 생성되어야 함
    assert len(recurring_instances) == 3

    # 각 인스턴스가 12월 25일인지 확인
    for instance in recurring_instances:
        assert instance.start_time.month == 12
        assert instance.start_time.day == 25


def test_start_date_not_in_byday(test_session, test_user):
    """시작 날짜가 BYDAY에 포함되지 않는 경우 테스트"""
    # 매주 화요일과 수요일 반복이지만, 시작 날짜는 월요일
    schedule_data = ScheduleCreate(
        title="주간 회의",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),  # 2024-01-01은 월요일
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        recurrence_rule="FREQ=WEEKLY;BYDAY=TU,WE",  # 화요일과 수요일만
    )

    service = ScheduleService(test_session, test_user)
    parent_schedule = service.create_schedule(schedule_data)

    # 1월 전체 조회
    start_date = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
    end_date = datetime(2024, 1, 31, 23, 59, 59, tzinfo=UTC)
    schedules = service.get_schedules_by_date_range(start_date, end_date)

    recurring_instances = [s for s in schedules if s.parent_id == parent_schedule.id]

    # 시작 날짜가 월요일이지만, 첫 번째 인스턴스는 다음 화요일(1/2)부터 시작되어야 함
    # 1월에는 화요일 5개, 수요일 5개 = 총 10개
    assert len(recurring_instances) == 10

    # 첫 번째 인스턴스가 화요일인지 확인
    first_instance = min(recurring_instances, key=lambda s: s.start_time)
    assert first_instance.start_time.weekday() == 1  # 화요일
    assert first_instance.start_time.date() == datetime(2024, 1, 2).date()

    # 모든 인스턴스가 화요일 또는 수요일인지 확인
    for instance in recurring_instances:
        weekday = instance.start_time.weekday()
        assert weekday in [1, 2], f"인스턴스는 화요일(1) 또는 수요일(2)이어야 함, 실제: {weekday}"


def test_count_vs_recurrence_end(test_session, test_user):
    """COUNT와 recurrence_end 동시 사용 시 우선순위 테스트"""
    # COUNT=5와 recurrence_end가 모두 있는 경우
    # COUNT가 우선되어야 함
    schedule_data = ScheduleCreate(
        title="주간 회의",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),  # 2024-01-01은 월요일
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        recurrence_rule="FREQ=WEEKLY;BYDAY=MO;COUNT=5",
        recurrence_end=datetime(2024, 3, 31, 23, 59, 59, tzinfo=UTC),  # COUNT보다 더 늦은 날짜
    )

    service = ScheduleService(test_session, test_user)
    parent_schedule = service.create_schedule(schedule_data)

    # 충분한 범위로 조회
    start_date = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
    end_date = datetime(2024, 3, 31, 23, 59, 59, tzinfo=UTC)
    schedules = service.get_schedules_by_date_range(start_date, end_date)

    recurring_instances = [s for s in schedules if s.parent_id == parent_schedule.id]

    # COUNT=5가 우선되어야 하므로 정확히 5개만 생성되어야 함
    assert len(recurring_instances) == 5

    # 모든 인스턴스가 1월에 있어야 함 (COUNT=5이므로)
    for instance in recurring_instances:
        assert instance.start_time.month == 1


def test_invalid_rrule_count_zero(test_session, test_user):
    """COUNT=0인 잘못된 RRULE 패턴 테스트"""
    schedule_data = ScheduleCreate(
        title="잘못된 반복 일정",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        recurrence_rule="FREQ=WEEKLY;BYDAY=MO;COUNT=0",
    )

    service = ScheduleService(test_session, test_user)
    with pytest.raises(InvalidRecurrenceRuleError):
        service.create_schedule(schedule_data)


def test_invalid_rrule_invalid_weekday(test_session, test_user):
    """잘못된 요일 코드를 사용하는 RRULE 패턴 테스트"""
    schedule_data = ScheduleCreate(
        title="잘못된 반복 일정",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        recurrence_rule="FREQ=WEEKLY;BYDAY=XX",  # 잘못된 요일 코드
    )

    service = ScheduleService(test_session, test_user)
    with pytest.raises(InvalidRecurrenceRuleError):
        service.create_schedule(schedule_data)


def test_invalid_rrule_invalid_freq(test_session, test_user):
    """잘못된 FREQ 값을 사용하는 RRULE 패턴 테스트"""
    schedule_data = ScheduleCreate(
        title="잘못된 반복 일정",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        recurrence_rule="FREQ=INVALID;BYDAY=MO",
    )

    service = ScheduleService(test_session, test_user)
    with pytest.raises(InvalidRecurrenceRuleError):
        service.create_schedule(schedule_data)
