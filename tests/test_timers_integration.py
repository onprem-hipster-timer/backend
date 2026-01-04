"""
Timer Integration Tests

DB를 포함한 타이머 통합 테스트
"""
from datetime import datetime, UTC

import pytest

from app.core.constants import TimerStatus
from app.domain.schedule.schema.dto import ScheduleCreate
from app.domain.schedule.service import ScheduleService
from app.domain.timer.schema.dto import TimerCreate
from app.domain.timer.service import TimerService


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
            title=f"타이머 {i + 1}",
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


@pytest.mark.integration
def test_create_timer_with_tags_integration(test_session):
    """타이머 생성 시 태그 함께 설정 통합 테스트"""
    from app.domain.tag.schema.dto import TagGroupCreate, TagCreate
    from app.domain.tag.service import TagService

    # 1. 일정 생성
    schedule_service = ScheduleService(test_session)
    schedule_data = ScheduleCreate(
        title="태그 테스트 일정",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
    )
    schedule = schedule_service.create_schedule(schedule_data)

    # 2. 그룹 및 태그 생성
    tag_service = TagService(test_session)
    group_data = TagGroupCreate(name="업무", color="#FF5733")
    group = tag_service.create_tag_group(group_data)

    tag_data = TagCreate(name="중요", color="#FF0000", group_id=group.id)
    tag = tag_service.create_tag(tag_data)

    # 3. 타이머 생성 시 태그 설정
    timer_service = TimerService(test_session)
    timer_data = TimerCreate(
        schedule_id=schedule.id,
        title="태그 테스트 타이머",
        allocated_duration=1800,
        tag_ids=[tag.id],
    )
    timer = timer_service.create_timer(timer_data)

    # 4. 타이머의 태그 확인
    timer_tags = tag_service.get_timer_tags(timer.id)
    assert len(timer_tags) == 1
    assert timer_tags[0].id == tag.id
    assert timer_tags[0].name == "중요"


@pytest.mark.integration
def test_update_timer_tags_integration(test_session):
    """타이머 수정 시 태그 업데이트 통합 테스트"""
    from app.domain.tag.schema.dto import TagGroupCreate, TagCreate
    from app.domain.tag.service import TagService
    from app.domain.timer.schema.dto import TimerUpdate

    # 1. 일정 및 타이머 생성
    schedule_service = ScheduleService(test_session)
    schedule_data = ScheduleCreate(
        title="태그 업데이트 테스트 일정",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
    )
    schedule = schedule_service.create_schedule(schedule_data)

    timer_service = TimerService(test_session)
    timer_data = TimerCreate(
        schedule_id=schedule.id,
        title="태그 업데이트 테스트 타이머",
        allocated_duration=1800,
    )
    timer = timer_service.create_timer(timer_data)

    # 2. 그룹 및 태그 생성
    tag_service = TagService(test_session)
    group_data = TagGroupCreate(name="업무", color="#FF5733")
    group = tag_service.create_tag_group(group_data)

    tag1_data = TagCreate(name="태그1", color="#FF0000", group_id=group.id)
    tag1 = tag_service.create_tag(tag1_data)

    tag2_data = TagCreate(name="태그2", color="#00FF00", group_id=group.id)
    tag2 = tag_service.create_tag(tag2_data)

    # 3. 타이머 태그 업데이트
    update_data = TimerUpdate(tag_ids=[tag1.id, tag2.id])
    updated_timer = timer_service.update_timer(timer.id, update_data)

    # 4. 타이머의 태그 확인
    timer_tags = tag_service.get_timer_tags(updated_timer.id)
    assert len(timer_tags) == 2
    tag_ids = [t.id for t in timer_tags]
    assert tag1.id in tag_ids
    assert tag2.id in tag_ids


@pytest.mark.integration
def test_timer_tags_workflow_integration(test_session):
    """타이머 태그 전체 워크플로우 통합 테스트"""
    from app.domain.tag.schema.dto import TagGroupCreate, TagCreate
    from app.domain.tag.service import TagService
    from app.domain.timer.schema.dto import TimerUpdate, TimerRead

    # 1. 일정 생성
    schedule_service = ScheduleService(test_session)
    schedule_data = ScheduleCreate(
        title="태그 워크플로우 테스트 일정",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
    )
    schedule = schedule_service.create_schedule(schedule_data)

    # 2. 그룹 및 태그 생성
    tag_service = TagService(test_session)
    group_data = TagGroupCreate(name="업무", color="#FF5733")
    group = tag_service.create_tag_group(group_data)

    tag1_data = TagCreate(name="태그1", color="#FF0000", group_id=group.id)
    tag1 = tag_service.create_tag(tag1_data)

    tag2_data = TagCreate(name="태그2", color="#00FF00", group_id=group.id)
    tag2 = tag_service.create_tag(tag2_data)

    # 3. 타이머 생성 시 태그 설정
    timer_service = TimerService(test_session)
    timer_data = TimerCreate(
        schedule_id=schedule.id,
        title="태그 워크플로우 타이머",
        allocated_duration=1800,
        tag_ids=[tag1.id],
    )
    timer = timer_service.create_timer(timer_data)

    # 4. 타이머 태그 확인
    timer_tags = tag_service.get_timer_tags(timer.id)
    assert len(timer_tags) == 1
    assert timer_tags[0].id == tag1.id

    # 5. 타이머 태그 업데이트
    update_data = TimerUpdate(tag_ids=[tag1.id, tag2.id])
    updated_timer = timer_service.update_timer(timer.id, update_data)
    timer_tags = tag_service.get_timer_tags(updated_timer.id)
    assert len(timer_tags) == 2

    # 6. 타이머 태그 제거
    remove_data = TimerUpdate(tag_ids=[])
    removed_timer = timer_service.update_timer(timer.id, remove_data)
    timer_tags = tag_service.get_timer_tags(removed_timer.id)
    assert len(timer_tags) == 0

    # 7. TimerRead에서 태그 확인 (include_tags=True)
    tags_read = [tag_service.get_timer_tags(timer.id)]
    timer_read = TimerRead.from_model(
        timer,
        include_tags=True,
        tags=tags_read[0] if tags_read[0] else [],
    )
    assert len(timer_read.tags) == 0  # 태그가 제거되었으므로 빈 배열


@pytest.mark.integration
def test_timer_include_tags_false_integration(test_session):
    """타이머 조회 시 include_tags=False일 때 tags가 빈 배열인지 통합 테스트"""
    from app.domain.timer.schema.dto import TimerRead
    from app.domain.tag.schema.dto import TagGroupCreate, TagCreate
    from app.domain.tag.service import TagService

    # 1. 일정 생성
    schedule_service = ScheduleService(test_session)
    schedule_data = ScheduleCreate(
        title="include_tags False 테스트 일정",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
    )
    schedule = schedule_service.create_schedule(schedule_data)

    # 2. 그룹 및 태그 생성
    tag_service = TagService(test_session)
    group_data = TagGroupCreate(name="업무", color="#FF5733")
    group = tag_service.create_tag_group(group_data)

    tag_data = TagCreate(name="중요", color="#FF0000", group_id=group.id)
    tag = tag_service.create_tag(tag_data)

    # 3. 타이머 생성 시 태그 설정
    timer_service = TimerService(test_session)
    timer_data = TimerCreate(
        schedule_id=schedule.id,
        title="include_tags False 테스트 타이머",
        allocated_duration=1800,
        tag_ids=[tag.id],
    )
    timer = timer_service.create_timer(timer_data)

    # 4. include_tags=False로 TimerRead 생성
    timer_read = TimerRead.from_model(
        timer,
        include_tags=False,
    )

    # 5. tags가 빈 배열인지 확인
    assert timer_read.tags == []
    assert timer_read.id == timer.id


@pytest.mark.integration
def test_timer_include_tags_true_integration(test_session):
    """타이머 조회 시 include_tags=True일 때 tags가 포함되는지 통합 테스트"""
    from app.domain.timer.schema.dto import TimerRead
    from app.domain.tag.schema.dto import TagGroupCreate, TagCreate, TagRead
    from app.domain.tag.service import TagService

    # 1. 일정 생성
    schedule_service = ScheduleService(test_session)
    schedule_data = ScheduleCreate(
        title="include_tags True 테스트 일정",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
    )
    schedule = schedule_service.create_schedule(schedule_data)

    # 2. 그룹 및 태그 생성
    tag_service = TagService(test_session)
    group_data = TagGroupCreate(name="업무", color="#FF5733")
    group = tag_service.create_tag_group(group_data)

    tag_data = TagCreate(name="중요", color="#FF0000", group_id=group.id)
    tag = tag_service.create_tag(tag_data)

    # 3. 타이머 생성 시 태그 설정
    timer_service = TimerService(test_session)
    timer_data = TimerCreate(
        schedule_id=schedule.id,
        title="include_tags True 테스트 타이머",
        allocated_duration=1800,
        tag_ids=[tag.id],
    )
    timer = timer_service.create_timer(timer_data)

    # 4. 태그 정보 조회
    tags = tag_service.get_timer_tags(timer.id)
    tags_read = [TagRead.model_validate(tag) for tag in tags]

    # 5. include_tags=True로 TimerRead 생성
    timer_read = TimerRead.from_model(
        timer,
        include_tags=True,
        tags=tags_read,
    )

    # 6. tags가 포함되어 있는지 확인
    assert len(timer_read.tags) == 1
    assert timer_read.tags[0].id == tag.id
    assert timer_read.tags[0].name == "중요"
    assert timer_read.id == timer.id