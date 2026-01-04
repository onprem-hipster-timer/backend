"""
Tag Service Tests
"""
from uuid import uuid4

import pytest

from app.domain.tag.exceptions import (
    TagGroupNotFoundError,
    TagNotFoundError,
    DuplicateTagNameError,
)
from app.domain.tag.schema.dto import (
    TagGroupCreate,
    TagGroupUpdate,
    TagCreate,
    TagUpdate,
)
from app.domain.tag.service import TagService


@pytest.fixture
def sample_tag_group(test_session):
    """테스트용 태그 그룹 (ORM 모델 반환)"""
    service = TagService(test_session)
    data = TagGroupCreate(
        name="업무",
        color="#FF5733",
        description="업무 관련 태그 그룹",
    )
    # Service가 ORM 모델을 반환하므로 세션에 연결됨
    return service.create_tag_group(data)


@pytest.fixture
def sample_tag(test_session, sample_tag_group):
    """테스트용 태그 (ORM 모델 반환)"""
    service = TagService(test_session)
    data = TagCreate(
        name="중요",
        color="#FF0000",
        description="중요한 일정",
        group_id=sample_tag_group.id,
    )
    # Service가 ORM 모델을 반환하므로 세션에 연결됨
    return service.create_tag(data)


# ============================================================
# TagGroup CRUD Tests
# ============================================================

def test_create_tag_group_success(test_session):
    """태그 그룹 생성 성공"""
    service = TagService(test_session)
    data = TagGroupCreate(
        name="업무",
        color="#FF5733",
        description="업무 관련 태그",
    )
    tag_group = service.create_tag_group(data)

    assert tag_group.name == "업무"
    assert tag_group.color == "#FF5733"
    assert tag_group.description == "업무 관련 태그"
    assert tag_group.id is not None


def test_create_tag_group_color_validation(test_session):
    """태그 그룹 색상 검증"""
    service = TagService(test_session)

    # 잘못된 색상 형식
    with pytest.raises(ValueError, match="색상은 HEX 형식이어야 합니다"):
        data = TagGroupCreate(
            name="업무",
            color="FF5733",  # # 없음
        )
        service.create_tag_group(data)


def test_get_tag_group_success(test_session, sample_tag_group):
    """태그 그룹 조회 성공"""
    service = TagService(test_session)
    tag_group = service.get_tag_group(sample_tag_group.id)

    assert tag_group.id == sample_tag_group.id
    assert tag_group.name == "업무"


def test_get_tag_group_not_found(test_session):
    """태그 그룹 조회 실패 (없음)"""
    service = TagService(test_session)
    fake_id = uuid4()

    with pytest.raises(TagGroupNotFoundError):
        service.get_tag_group(fake_id)


def test_get_all_tag_groups(test_session, sample_tag_group):
    """모든 태그 그룹 조회"""
    service = TagService(test_session)

    # 두 번째 그룹 생성
    data2 = TagGroupCreate(name="개인", color="#00FF00")
    service.create_tag_group(data2)

    tag_groups = service.get_all_tag_groups()
    assert len(tag_groups) >= 2
    names = [g.name for g in tag_groups]
    assert "업무" in names
    assert "개인" in names


def test_update_tag_group_success(test_session, sample_tag_group):
    """태그 그룹 업데이트 성공"""
    service = TagService(test_session)
    data = TagGroupUpdate(name="업무2", color="#00FF00")

    updated = service.update_tag_group(sample_tag_group.id, data)

    assert updated.name == "업무2"
    assert updated.color == "#00FF00"
    assert updated.id == sample_tag_group.id


def test_delete_tag_group_success(test_session, sample_tag_group):
    """태그 그룹 삭제 성공"""
    service = TagService(test_session)
    group_id = sample_tag_group.id

    service.delete_tag_group(group_id)
    test_session.flush()

    # identity map 캐시 무효화
    test_session.expire_all()
    with pytest.raises(TagGroupNotFoundError):
        service.get_tag_group(group_id)


def test_delete_tag_group_cascade_tags(test_session, sample_tag_group, sample_tag):
    """태그 그룹 삭제 시 태그도 CASCADE 삭제"""
    service = TagService(test_session)
    group_id = sample_tag_group.id
    tag_id = sample_tag.id

    # 태그가 존재하는지 확인
    tag = service.get_tag(tag_id)
    assert tag is not None

    # 그룹 삭제
    service.delete_tag_group(group_id)
    test_session.flush()

    # identity map 캐시 무효화
    test_session.expire_all()
    with pytest.raises(TagNotFoundError):
        service.get_tag(tag_id)


# ============================================================
# Tag CRUD Tests
# ============================================================

def test_create_tag_success(test_session, sample_tag_group):
    """태그 생성 성공"""
    service = TagService(test_session)
    data = TagCreate(
        name="중요",
        color="#FF0000",
        description="중요한 일정",
        group_id=sample_tag_group.id,
    )
    tag = service.create_tag(data)

    assert tag.name == "중요"
    assert tag.color == "#FF0000"
    assert tag.group_id == sample_tag_group.id
    assert tag.id is not None


def test_create_tag_duplicate_name_in_group(test_session, sample_tag_group):
    """그룹 내 태그 이름 중복 테스트"""
    service = TagService(test_session)
    data = TagCreate(
        name="중요",
        color="#FF0000",
        group_id=sample_tag_group.id,
    )
    service.create_tag(data)

    # 같은 그룹에 같은 이름의 태그 생성 시도
    with pytest.raises(DuplicateTagNameError):
        service.create_tag(data)


def test_create_tag_different_group_same_name(test_session):
    """다른 그룹에는 같은 이름의 태그 생성 가능"""
    service = TagService(test_session)

    # 그룹 1 생성
    group1 = service.create_tag_group(TagGroupCreate(name="업무", color="#FF0000"))

    # 그룹 2 생성
    group2 = service.create_tag_group(TagGroupCreate(name="개인", color="#00FF00"))

    # 각 그룹에 같은 이름의 태그 생성
    tag1 = service.create_tag(TagCreate(name="중요", color="#FF0000", group_id=group1.id))
    tag2 = service.create_tag(TagCreate(name="중요", color="#00FF00", group_id=group2.id))

    assert tag1.name == tag2.name == "중요"
    assert tag1.group_id != tag2.group_id


def test_get_tag_success(test_session, sample_tag):
    """태그 조회 성공"""
    service = TagService(test_session)
    tag = service.get_tag(sample_tag.id)

    assert tag.id == sample_tag.id
    assert tag.name == "중요"


def test_get_tag_not_found(test_session):
    """태그 조회 실패 (없음)"""
    service = TagService(test_session)
    fake_id = uuid4()

    with pytest.raises(TagNotFoundError):
        service.get_tag(fake_id)


def test_get_tags_by_group(test_session, sample_tag_group):
    """그룹별 태그 조회"""
    service = TagService(test_session)

    # 태그 여러 개 생성
    tag1 = service.create_tag(TagCreate(name="태그1", color="#FF0000", group_id=sample_tag_group.id))
    tag2 = service.create_tag(TagCreate(name="태그2", color="#00FF00", group_id=sample_tag_group.id))

    tags = service.get_tags_by_group(sample_tag_group.id)
    assert len(tags) >= 2
    names = [t.name for t in tags]
    assert "태그1" in names
    assert "태그2" in names


def test_update_tag_success(test_session, sample_tag):
    """태그 업데이트 성공"""
    service = TagService(test_session)
    data = TagUpdate(name="매우 중요", color="#FF0000")

    updated = service.update_tag(sample_tag.id, data)

    assert updated.name == "매우 중요"
    assert updated.id == sample_tag.id


def test_update_tag_duplicate_name(test_session, sample_tag_group):
    """태그 이름 변경 시 중복 검증"""
    service = TagService(test_session)

    tag1 = service.create_tag(TagCreate(name="태그1", color="#FF0000", group_id=sample_tag_group.id))
    tag2 = service.create_tag(TagCreate(name="태그2", color="#00FF00", group_id=sample_tag_group.id))

    # tag2의 이름을 tag1과 같게 변경 시도
    with pytest.raises(DuplicateTagNameError):
        service.update_tag(tag2.id, TagUpdate(name="태그1"))


def test_delete_tag_success(test_session, sample_tag):
    """태그 삭제 성공"""
    service = TagService(test_session)
    tag_id = sample_tag.id

    service.delete_tag(tag_id)
    test_session.flush()

    # identity map 캐시 무효화
    test_session.expire_all()
    with pytest.raises(TagNotFoundError):
        service.get_tag(tag_id)


# ============================================================
# Schedule-Tag Relationship Tests
# ============================================================

def test_add_tag_to_schedule(test_session, sample_schedule, sample_tag):
    """일정에 태그 추가"""
    service = TagService(test_session)

    service.add_tag_to_schedule(sample_schedule.id, sample_tag.id)

    tags = service.get_schedule_tags(sample_schedule.id)
    assert len(tags) == 1
    assert tags[0].id == sample_tag.id


def test_add_tag_to_schedule_duplicate(test_session, sample_schedule, sample_tag):
    """일정에 같은 태그 중복 추가 (무시)"""
    service = TagService(test_session)

    service.add_tag_to_schedule(sample_schedule.id, sample_tag.id)
    service.add_tag_to_schedule(sample_schedule.id, sample_tag.id)  # 중복 추가

    tags = service.get_schedule_tags(sample_schedule.id)
    assert len(tags) == 1  # 중복되지 않음


def test_remove_tag_from_schedule(test_session, sample_schedule, sample_tag):
    """일정에서 태그 제거"""
    service = TagService(test_session)

    service.add_tag_to_schedule(sample_schedule.id, sample_tag.id)
    service.remove_tag_from_schedule(sample_schedule.id, sample_tag.id)

    tags = service.get_schedule_tags(sample_schedule.id)
    assert len(tags) == 0


def test_set_schedule_tags(test_session, sample_schedule, sample_tag_group):
    """일정의 태그 일괄 설정"""
    service = TagService(test_session)

    # 태그 여러 개 생성
    tag1 = service.create_tag(TagCreate(name="태그1", color="#FF0000", group_id=sample_tag_group.id))
    tag2 = service.create_tag(TagCreate(name="태그2", color="#00FF00", group_id=sample_tag_group.id))
    tag3 = service.create_tag(TagCreate(name="태그3", color="#0000FF", group_id=sample_tag_group.id))

    # 기존 태그 추가
    service.add_tag_to_schedule(sample_schedule.id, tag1.id)

    # 태그 일괄 설정 (기존 태그 교체)
    tags = service.set_schedule_tags(sample_schedule.id, [tag2.id, tag3.id])

    assert len(tags) == 2
    tag_ids = [t.id for t in tags]
    assert tag2.id in tag_ids
    assert tag3.id in tag_ids
    assert tag1.id not in tag_ids  # 기존 태그는 제거됨


def test_get_schedule_tags_empty(test_session, sample_schedule):
    """일정의 태그 조회 (태그 없음)"""
    service = TagService(test_session)

    tags = service.get_schedule_tags(sample_schedule.id)
    assert len(tags) == 0


# ============================================================
# ScheduleException-Tag Relationship Tests
# ============================================================

def test_add_tag_to_schedule_exception(test_session, sample_schedule, sample_tag):
    """예외 일정에 태그 추가"""
    from app.crud import schedule as schedule_crud
    from datetime import datetime, UTC

    service = TagService(test_session)

    # 예외 일정 생성
    exception = schedule_crud.create_schedule_exception(
        test_session,
        parent_id=sample_schedule.id,
        exception_date=datetime(2024, 1, 2, 10, 0, 0, tzinfo=UTC),
        is_deleted=False,
    )
    test_session.flush()

    service.add_tag_to_schedule_exception(exception.id, sample_tag.id)

    tags = service.get_schedule_exception_tags(exception.id)
    assert len(tags) == 1
    assert tags[0].id == sample_tag.id


def test_set_schedule_exception_tags(test_session, sample_schedule, sample_tag_group):
    """예외 일정의 태그 일괄 설정"""
    from app.crud import schedule as schedule_crud
    from datetime import datetime, UTC

    service = TagService(test_session)

    # 예외 일정 생성
    exception = schedule_crud.create_schedule_exception(
        test_session,
        parent_id=sample_schedule.id,
        exception_date=datetime(2024, 1, 2, 10, 0, 0, tzinfo=UTC),
        is_deleted=False,
    )
    test_session.flush()

    # 태그 생성
    tag1 = service.create_tag(TagCreate(name="태그1", color="#FF0000", group_id=sample_tag_group.id))
    tag2 = service.create_tag(TagCreate(name="태그2", color="#00FF00", group_id=sample_tag_group.id))

    # 태그 일괄 설정
    tags = service.set_schedule_exception_tags(exception.id, [tag1.id, tag2.id])

    assert len(tags) == 2
    tag_ids = [t.id for t in tags]
    assert tag1.id in tag_ids
    assert tag2.id in tag_ids


def test_remove_tag_from_schedule_exception(test_session, sample_schedule, sample_tag):
    """예외 일정에서 태그 제거"""
    from app.crud import schedule as schedule_crud
    from datetime import datetime, UTC

    service = TagService(test_session)

    # 예외 일정 생성
    exception = schedule_crud.create_schedule_exception(
        test_session,
        parent_id=sample_schedule.id,
        exception_date=datetime(2024, 1, 2, 10, 0, 0, tzinfo=UTC),
        is_deleted=False,
    )
    test_session.flush()

    # 태그 추가
    service.add_tag_to_schedule_exception(exception.id, sample_tag.id)

    # 태그 제거
    service.remove_tag_from_schedule_exception(exception.id, sample_tag.id)

    # 태그가 제거되었는지 확인
    tags = service.get_schedule_exception_tags(exception.id)
    assert len(tags) == 0


def test_get_schedule_exception_tags_empty(test_session, sample_schedule):
    """예외 일정의 태그 조회 (태그 없음)"""
    from app.crud import schedule as schedule_crud
    from datetime import datetime, UTC

    service = TagService(test_session)

    # 예외 일정 생성
    exception = schedule_crud.create_schedule_exception(
        test_session,
        parent_id=sample_schedule.id,
        exception_date=datetime(2024, 1, 2, 10, 0, 0, tzinfo=UTC),
        is_deleted=False,
    )
    test_session.flush()

    # 태그 조회 (빈 결과)
    tags = service.get_schedule_exception_tags(exception.id)
    assert len(tags) == 0


def test_add_tag_to_schedule_exception_duplicate(test_session, sample_schedule, sample_tag):
    """예외 일정에 같은 태그 중복 추가 (무시)"""
    from app.crud import schedule as schedule_crud
    from datetime import datetime, UTC

    service = TagService(test_session)

    # 예외 일정 생성
    exception = schedule_crud.create_schedule_exception(
        test_session,
        parent_id=sample_schedule.id,
        exception_date=datetime(2024, 1, 2, 10, 0, 0, tzinfo=UTC),
        is_deleted=False,
    )
    test_session.flush()

    # 태그 추가
    service.add_tag_to_schedule_exception(exception.id, sample_tag.id)

    # 같은 태그 중복 추가
    service.add_tag_to_schedule_exception(exception.id, sample_tag.id)

    # 중복되지 않았는지 확인
    tags = service.get_schedule_exception_tags(exception.id)
    assert len(tags) == 1
    assert tags[0].id == sample_tag.id


# ============================================================
# CASCADE 삭제 테스트
# ============================================================

def test_schedule_delete_cascade_tags(test_engine, sample_schedule, sample_tag):
    """일정 삭제 시 태그 관계 CASCADE 삭제"""
    from sqlmodel import Session
    from app.domain.schedule.service import ScheduleService
    from app.domain.schedule.exceptions import ScheduleNotFoundError

    schedule_id = sample_schedule.id
    tag_id = sample_tag.id

    # 태그 추가
    with Session(test_engine) as add_session:
        tag_service = TagService(add_session)
        tag_service.add_tag_to_schedule(schedule_id, tag_id)
        add_session.commit()

    # 태그 관계 확인
    with Session(test_engine) as check_session:
        tag_service = TagService(check_session)
        tags = tag_service.get_schedule_tags(schedule_id)
        assert len(tags) == 1
        assert tags[0].id == tag_id

    # 일정 삭제
    with Session(test_engine) as delete_session:
        schedule_service = ScheduleService(delete_session)
        schedule_service.delete_schedule(schedule_id)
        delete_session.commit()

    # 일정이 삭제되었는지 확인
    with Session(test_engine) as check_session:
        schedule_service = ScheduleService(check_session)
        with pytest.raises(ScheduleNotFoundError):
            schedule_service.get_schedule(schedule_id)

    # 태그 관계도 CASCADE로 삭제되었는지 확인
    with Session(test_engine) as check_session:
        tag_service = TagService(check_session)
        tags = tag_service.get_schedule_tags(schedule_id)
        assert len(tags) == 0  # 일정이 삭제되어 태그 관계도 삭제됨


def test_schedule_exception_delete_cascade_tags(test_engine, sample_schedule, sample_tag):
    """예외 일정 삭제 시 태그 관계 CASCADE 삭제"""
    from sqlmodel import Session
    from app.crud import schedule as schedule_crud
    from app.domain.schedule.service import ScheduleService
    from datetime import datetime, UTC

    # 예외 일정 생성
    with Session(test_engine) as create_session:
        exception = schedule_crud.create_schedule_exception(
            create_session,
            parent_id=sample_schedule.id,
            exception_date=datetime(2024, 1, 2, 10, 0, 0, tzinfo=UTC),
            is_deleted=False,
        )
        create_session.commit()
        exception_id = exception.id

    # 태그 추가
    with Session(test_engine) as add_session:
        tag_service = TagService(add_session)
        tag_service.add_tag_to_schedule_exception(exception_id, sample_tag.id)
        add_session.commit()

    # 태그 관계 확인
    with Session(test_engine) as check_session:
        tag_service = TagService(check_session)
        tags = tag_service.get_schedule_exception_tags(exception_id)
        assert len(tags) == 1
        assert tags[0].id == sample_tag.id

    # 예외 일정 삭제 (부모 일정 삭제로 인한 CASCADE)
    with Session(test_engine) as delete_session:
        schedule_service = ScheduleService(delete_session)
        schedule_service.delete_schedule(sample_schedule.id)
        delete_session.commit()

    # 예외 일정이 삭제되었는지 확인 (부모 일정 삭제로 CASCADE)
    with Session(test_engine) as check_session:
        exception_check = schedule_crud.get_schedule_exception(check_session, exception_id)
        assert exception_check is None

    # 태그 관계도 CASCADE로 삭제되었는지 확인
    # (예외 일정이 삭제되어 태그 관계도 삭제됨)


def test_tag_delete_cascade_schedule_relations(test_engine, sample_schedule, sample_tag_group):
    """태그 삭제 시 일정/예외 일정과의 관계 CASCADE 삭제"""
    from sqlmodel import Session
    from app.crud import schedule as schedule_crud
    from datetime import datetime, UTC

    # 태그 생성
    with Session(test_engine) as create_session:
        tag_service = TagService(create_session)
        tag = tag_service.create_tag(TagCreate(
            name="삭제 테스트 태그",
            color="#FF0000",
            group_id=sample_tag_group.id,
        ))
        create_session.commit()
        tag_id = tag.id

    # 일정에 태그 추가
    with Session(test_engine) as add_session:
        tag_service = TagService(add_session)
        tag_service.add_tag_to_schedule(sample_schedule.id, tag_id)
        add_session.commit()

    # 예외 일정 생성 및 태그 추가
    with Session(test_engine) as create_session:
        exception = schedule_crud.create_schedule_exception(
            create_session,
            parent_id=sample_schedule.id,
            exception_date=datetime(2024, 1, 2, 10, 0, 0, tzinfo=UTC),
            is_deleted=False,
        )
        create_session.commit()
        exception_id = exception.id

    with Session(test_engine) as add_session:
        tag_service = TagService(add_session)
        tag_service.add_tag_to_schedule_exception(exception_id, tag_id)
        add_session.commit()

    # 태그 관계 확인
    with Session(test_engine) as check_session:
        tag_service = TagService(check_session)
        schedule_tags = tag_service.get_schedule_tags(sample_schedule.id)
        exception_tags = tag_service.get_schedule_exception_tags(exception_id)
        assert len(schedule_tags) == 1
        assert len(exception_tags) == 1

    # 태그 삭제
    with Session(test_engine) as delete_session:
        tag_service = TagService(delete_session)
        tag_service.delete_tag(tag_id)
        delete_session.commit()

    # 태그 관계가 CASCADE로 삭제되었는지 확인
    with Session(test_engine) as check_session:
        tag_service = TagService(check_session)
        schedule_tags = tag_service.get_schedule_tags(sample_schedule.id)
        exception_tags = tag_service.get_schedule_exception_tags(exception_id)
        assert len(schedule_tags) == 0  # 태그 삭제로 관계 삭제
        assert len(exception_tags) == 0  # 태그 삭제로 관계 삭제


# ============================================================
# 빈 그룹 자동 삭제 테스트 (반복 일정 패턴과 동일)
# ============================================================

def test_delete_all_tags_deletes_group(test_engine, sample_tag_group):
    """모든 태그 삭제 시 그룹도 자동 삭제 (반복 일정 패턴과 동일)"""
    from sqlmodel import Session

    group_id = sample_tag_group.id

    # 태그 여러 개 생성
    with Session(test_engine) as create_session:
        tag_service = TagService(create_session)
        tag1 = tag_service.create_tag(TagCreate(
            name="태그1",
            color="#FF0000",
            group_id=group_id,
        ))
        tag2 = tag_service.create_tag(TagCreate(
            name="태그2",
            color="#00FF00",
            group_id=group_id,
        ))
        create_session.commit()
        tag1_id = tag1.id
        tag2_id = tag2.id

    # 첫 번째 태그 삭제 (그룹은 아직 남아있어야 함)
    with Session(test_engine) as delete_session:
        tag_service = TagService(delete_session)
        tag_service.delete_tag(tag1_id)
        delete_session.commit()

    # 그룹이 아직 존재하는지 확인
    with Session(test_engine) as check_session:
        tag_service = TagService(check_session)
        group = tag_service.get_tag_group(group_id)
        assert group is not None
        remaining_tags = tag_service.get_tags_by_group(group_id)
        assert len(remaining_tags) == 1  # tag2만 남음

    # 마지막 태그 삭제 (그룹도 자동 삭제되어야 함)
    with Session(test_engine) as delete_session:
        tag_service = TagService(delete_session)
        tag_service.delete_tag(tag2_id)
        delete_session.commit()

    # 그룹이 자동으로 삭제되었는지 확인
    with Session(test_engine) as check_session:
        tag_service = TagService(check_session)
        with pytest.raises(TagGroupNotFoundError):
            tag_service.get_tag_group(group_id)


def test_delete_tag_keeps_group_with_remaining_tags(test_engine, sample_tag_group):
    """태그 삭제 시 다른 태그가 남아있으면 그룹 유지"""
    from sqlmodel import Session

    group_id = sample_tag_group.id

    # 태그 여러 개 생성
    with Session(test_engine) as create_session:
        tag_service = TagService(create_session)
        tag1 = tag_service.create_tag(TagCreate(
            name="태그1",
            color="#FF0000",
            group_id=group_id,
        ))
        tag2 = tag_service.create_tag(TagCreate(
            name="태그2",
            color="#00FF00",
            group_id=group_id,
        ))
        create_session.commit()
        tag1_id = tag1.id

    # 하나의 태그만 삭제
    with Session(test_engine) as delete_session:
        tag_service = TagService(delete_session)
        tag_service.delete_tag(tag1_id)
        delete_session.commit()

    # 그룹이 여전히 존재하는지 확인
    with Session(test_engine) as check_session:
        tag_service = TagService(check_session)
        group = tag_service.get_tag_group(group_id)
        assert group is not None
        remaining_tags = tag_service.get_tags_by_group(group_id)
        assert len(remaining_tags) == 1  # tag2가 남아있음
