"""
Tag Service Tests
"""
from uuid import UUID, uuid4

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

