from datetime import datetime, UTC, timezone, timedelta
from uuid import UUID

import pytest

from app.domain.dateutil.service import ensure_utc_naive
from app.domain.schedule.schema.dto import ScheduleCreate, ScheduleUpdate
from app.domain.schedule.service import ScheduleService
from app.utils.validators import validate_time_order


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


def test_create_schedule_success(test_session, test_user):
    """일정 생성 성공 테스트"""

    schedule_data = ScheduleCreate(
        title="회의",
        description="팀 회의",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
    )

    service = ScheduleService(test_session, test_user)
    schedule = service.create_schedule(schedule_data)

    # DTO가 UTC naive datetime으로 변환하여 저장
    expected_start_time = ensure_utc_naive(schedule_data.start_time)
    expected_end_time = ensure_utc_naive(schedule_data.end_time)

    assert schedule.title == "회의"
    assert schedule.description == "팀 회의"
    assert schedule.start_time == expected_start_time
    assert schedule.end_time == expected_end_time
    assert isinstance(schedule.id, UUID)
    assert schedule.created_at is not None


def test_create_schedule_invalid_time(test_session):
    """잘못된 시간으로 일정 생성 실패 테스트"""
    from pydantic import ValidationError

    # Pydantic validator가 객체 생성 시점에서 검증
    # FastAPI는 이를 자동으로 422로 변환
    with pytest.raises(ValidationError) as exc_info:
        schedule_data = ScheduleCreate(
            title="회의",
            start_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            end_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),  # end_time < start_time
        )

    # ValidationError의 에러 메시지 확인
    assert "end_time must be after start_time" in str(exc_info.value)


def test_get_schedules(test_session, sample_schedule, test_user):
    """날짜 범위 기반 일정 조회 테스트"""
    from datetime import UTC

    service = ScheduleService(test_session, test_user)

    # 날짜 범위로 일정 조회 (sample_schedule이 포함되는 범위)
    start_date = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
    end_date = datetime(2024, 1, 1, 23, 59, 59, tzinfo=UTC)
    schedules = service.get_schedules_by_date_range(start_date, end_date)

    assert len(schedules) >= 1
    assert any(s.id == sample_schedule.id for s in schedules)


def test_get_schedule_success(test_session, sample_schedule, test_user):
    """ID로 일정 조회 성공 테스트"""
    service = ScheduleService(test_session, test_user)
    schedule = service.get_schedule(sample_schedule.id)

    assert schedule is not None
    assert schedule.id == sample_schedule.id
    assert schedule.title == sample_schedule.title


def test_get_schedule_not_found(test_session, test_user):
    """존재하지 않는 일정 조회 테스트"""
    from uuid import uuid4
    from app.domain.schedule.exceptions import ScheduleNotFoundError

    service = ScheduleService(test_session, test_user)
    non_existent_id = uuid4()

    with pytest.raises(ScheduleNotFoundError):
        service.get_schedule(non_existent_id)


def test_update_schedule_success(test_session, sample_schedule, test_user):
    """일정 업데이트 성공 테스트"""
    update_data = ScheduleUpdate(
        title="업데이트된 회의",
        description="업데이트된 설명",
    )

    service = ScheduleService(test_session, test_user)
    updated_schedule = service.update_schedule(sample_schedule.id, update_data)

    assert updated_schedule.title == "업데이트된 회의"
    assert updated_schedule.description == "업데이트된 설명"
    assert updated_schedule.id == sample_schedule.id


def test_update_schedule_invalid_time(test_session, sample_schedule):
    """잘못된 시간으로 일정 업데이트 실패 테스트"""
    from pydantic import ValidationError

    # Pydantic validator가 객체 생성 시점에서 검증
    # FastAPI는 이를 자동으로 422로 변환
    with pytest.raises(ValidationError) as exc_info:
        update_data = ScheduleUpdate(
            start_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            end_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),  # end_time < start_time
        )

    # ValidationError의 에러 메시지 확인
    assert "end_time must be after start_time" in str(exc_info.value)


def test_delete_schedule_success(test_engine, sample_schedule, test_user):
    """일정 삭제 성공 테스트"""
    from sqlmodel import Session
    from app.domain.schedule.exceptions import ScheduleNotFoundError

    schedule_id = sample_schedule.id

    # 삭제용 세션으로 일정 삭제
    with Session(test_engine) as delete_session:
        delete_service = ScheduleService(delete_session, test_user)
        delete_service.delete_schedule(schedule_id)
        delete_session.commit()  # 실제 DB에 반영

    # 조회용 다른 세션으로 실제 DB에서 확인 (identity map 없이)
    with Session(test_engine) as check_session:
        check_service = ScheduleService(check_session, test_user)
        with pytest.raises(ScheduleNotFoundError):
            check_service.get_schedule(schedule_id)


# ==================== UTC 변환 검증 테스트 ====================

def test_create_schedule_utc_conversion_kst(test_session, test_user):
    """KST timezone이 UTC naive로 변환되어 저장되는지 검증"""
    # KST는 UTC+9
    kst = timezone(timedelta(hours=9))
    kst_start = datetime(2024, 1, 1, 19, 0, 0, tzinfo=kst)  # KST 19:00
    kst_end = datetime(2024, 1, 1, 21, 0, 0, tzinfo=kst)  # KST 21:00

    schedule_data = ScheduleCreate(
        title="KST 일정",
        description="KST timezone 테스트",
        start_time=kst_start,
        end_time=kst_end,
    )

    service = ScheduleService(test_session, test_user)
    schedule = service.create_schedule(schedule_data)

    # KST 19:00 = UTC 10:00, KST 21:00 = UTC 12:00
    assert schedule.start_time.tzinfo is None  # naive datetime
    assert schedule.end_time.tzinfo is None  # naive datetime
    assert schedule.start_time == datetime(2024, 1, 1, 10, 0, 0)
    assert schedule.end_time == datetime(2024, 1, 1, 12, 0, 0)


def test_create_schedule_utc_conversion_est(test_session, test_user):
    """EST timezone이 UTC naive로 변환되어 저장되는지 검증"""
    # EST는 UTC-5
    est = timezone(timedelta(hours=-5))
    est_start = datetime(2024, 1, 1, 5, 0, 0, tzinfo=est)  # EST 05:00
    est_end = datetime(2024, 1, 1, 7, 0, 0, tzinfo=est)  # EST 07:00

    schedule_data = ScheduleCreate(
        title="EST 일정",
        description="EST timezone 테스트",
        start_time=est_start,
        end_time=est_end,
    )

    service = ScheduleService(test_session, test_user)
    schedule = service.create_schedule(schedule_data)

    # EST 05:00 = UTC 10:00, EST 07:00 = UTC 12:00
    assert schedule.start_time.tzinfo is None
    assert schedule.end_time.tzinfo is None
    assert schedule.start_time == datetime(2024, 1, 1, 10, 0, 0)
    assert schedule.end_time == datetime(2024, 1, 1, 12, 0, 0)


def test_create_schedule_utc_conversion_naive(test_session, test_user):
    """naive datetime이 그대로 저장되는지 검증 (UTC로 가정)"""
    naive_start = datetime(2024, 1, 1, 10, 0, 0)
    naive_end = datetime(2024, 1, 1, 12, 0, 0)

    schedule_data = ScheduleCreate(
        title="Naive 일정",
        description="Naive datetime 테스트",
        start_time=naive_start,
        end_time=naive_end,
    )

    service = ScheduleService(test_session, test_user)
    schedule = service.create_schedule(schedule_data)

    # naive datetime은 그대로 저장되어야 함
    assert schedule.start_time.tzinfo is None
    assert schedule.end_time.tzinfo is None
    assert schedule.start_time == naive_start
    assert schedule.end_time == naive_end


def test_update_schedule_utc_conversion_kst(test_session, sample_schedule, test_user):
    """업데이트 시 KST timezone이 UTC naive로 변환되는지 검증"""
    kst = timezone(timedelta(hours=9))
    kst_start = datetime(2024, 1, 2, 19, 0, 0, tzinfo=kst)  # KST 19:00
    kst_end = datetime(2024, 1, 2, 21, 0, 0, tzinfo=kst)  # KST 21:00

    update_data = ScheduleUpdate(
        start_time=kst_start,
        end_time=kst_end,
    )

    service = ScheduleService(test_session, test_user)
    updated_schedule = service.update_schedule(sample_schedule.id, update_data)

    # KST 19:00 = UTC 10:00, KST 21:00 = UTC 12:00
    assert updated_schedule.start_time.tzinfo is None
    assert updated_schedule.end_time.tzinfo is None
    assert updated_schedule.start_time == datetime(2024, 1, 2, 10, 0, 0)
    assert updated_schedule.end_time == datetime(2024, 1, 2, 12, 0, 0)


def test_update_schedule_utc_conversion_partial(test_session, sample_schedule, test_user):
    """부분 업데이트 시에도 UTC 변환이 적용되는지 검증"""
    kst = timezone(timedelta(hours=9))
    # 기존 end_time(2024-01-01 12:00)보다 이전으로 설정
    kst_start = datetime(2024, 1, 1, 18, 0, 0, tzinfo=kst)  # KST 18:00 = UTC 09:00

    # start_time만 업데이트
    update_data = ScheduleUpdate(
        start_time=kst_start,
    )

    service = ScheduleService(test_session, test_user)
    updated_schedule = service.update_schedule(sample_schedule.id, update_data)

    # start_time만 UTC로 변환되어야 함
    assert updated_schedule.start_time.tzinfo is None
    assert updated_schedule.start_time == datetime(2024, 1, 1, 9, 0, 0)  # UTC 09:00
    # end_time은 기존 값 유지
    assert updated_schedule.end_time == sample_schedule.end_time
    # start_time < end_time 검증
    assert updated_schedule.start_time < updated_schedule.end_time


def test_get_schedules_by_date_range_utc_conversion(test_session, test_user):
    """날짜 범위 조회 시 UTC 변환이 적용되는지 검증"""
    # UTC naive datetime으로 일정 생성
    schedule1 = ScheduleCreate(
        title="일정 1",
        start_time=datetime(2024, 1, 1, 10, 0, 0),
        end_time=datetime(2024, 1, 1, 12, 0, 0),
    )

    schedule2 = ScheduleCreate(
        title="일정 2",
        start_time=datetime(2024, 1, 2, 10, 0, 0),
        end_time=datetime(2024, 1, 2, 12, 0, 0),
    )

    service = ScheduleService(test_session, test_user)
    service.create_schedule(schedule1)
    service.create_schedule(schedule2)

    # KST timezone으로 조회 범위 지정
    kst = timezone(timedelta(hours=9))
    # KST 2024-01-01 00:00 ~ 23:59 = UTC 2023-12-31 15:00 ~ 2024-01-01 14:59
    kst_start = datetime(2024, 1, 1, 0, 0, 0, tzinfo=kst)
    kst_end = datetime(2024, 1, 1, 23, 59, 59, tzinfo=kst)

    # UTC로 변환되어 조회되어야 함
    schedules = service.get_schedules_by_date_range(kst_start, kst_end)

    # UTC 10:00 ~ 12:00은 KST 19:00 ~ 21:00이므로 범위에 포함되어야 함
    assert len(schedules) >= 1
    assert any(s.title == "일정 1" for s in schedules)


def test_utc_conversion_preserves_time_value(test_session, test_user):
    """다양한 timezone에서 같은 UTC 시간으로 변환되는지 검증"""
    # 같은 UTC 시간을 나타내는 다양한 timezone
    utc_dt = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    kst = timezone(timedelta(hours=9))
    kst_dt = datetime(2024, 1, 1, 19, 0, 0, tzinfo=kst)  # KST 19:00 = UTC 10:00
    est = timezone(timedelta(hours=-5))
    est_dt = datetime(2024, 1, 1, 5, 0, 0, tzinfo=est)  # EST 05:00 = UTC 10:00

    # 각각 다른 timezone으로 일정 생성
    schedule_utc = ScheduleCreate(
        title="UTC 일정",
        start_time=utc_dt,
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )

    schedule_kst = ScheduleCreate(
        title="KST 일정",
        start_time=kst_dt,
        end_time=datetime(2024, 1, 1, 21, 0, 0, tzinfo=kst),
    )

    schedule_est = ScheduleCreate(
        title="EST 일정",
        start_time=est_dt,
        end_time=datetime(2024, 1, 1, 7, 0, 0, tzinfo=est),
    )

    service = ScheduleService(test_session, test_user)
    created_utc = service.create_schedule(schedule_utc)
    created_kst = service.create_schedule(schedule_kst)
    created_est = service.create_schedule(schedule_est)

    # 모두 같은 UTC naive datetime으로 저장되어야 함
    assert created_utc.start_time == created_kst.start_time == created_est.start_time
    assert created_utc.start_time == datetime(2024, 1, 1, 10, 0, 0)
