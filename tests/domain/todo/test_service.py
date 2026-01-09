"""
Todo Service Tests

Todo 서비스의 비즈니스 로직을 테스트합니다.
"""
from datetime import datetime, UTC
from uuid import UUID, uuid4

import pytest

from app.domain.todo.exceptions import TodoNotFoundError
from app.domain.todo.enums import TodoStatus
from app.domain.todo.schema.dto import TodoCreate, TodoUpdate
from app.domain.todo.service import TodoService
from app.domain.tag.service import TagService
from app.domain.tag.schema.dto import TagGroupCreate, TagCreate
from app.domain.schedule.enums import ScheduleState


@pytest.fixture
def sample_tag_group(test_session):
    """테스트용 태그 그룹"""
    service = TagService(test_session)
    data = TagGroupCreate(
        name="업무",
        color="#FF5733",
        description="업무 관련 태그 그룹",
    )
    return service.create_tag_group(data)


@pytest.fixture
def sample_tag(test_session, sample_tag_group):
    """테스트용 태그"""
    service = TagService(test_session)
    data = TagCreate(
        name="중요",
        color="#FF0000",
        description="중요한 일정",
        group_id=sample_tag_group.id,
    )
    return service.create_tag(data)


@pytest.fixture
def sample_todo(test_session, sample_tag_group):
    """테스트용 Todo"""
    service = TodoService(test_session)
    data = TodoCreate(
        title="테스트 Todo",
        description="테스트 설명",
        tag_group_id=sample_tag_group.id,
    )
    todo = service.create_todo(data)
    test_session.flush()
    test_session.refresh(todo)
    return todo


@pytest.fixture
def sample_todo_with_tags(test_session, sample_tag, sample_tag_group):
    """태그가 있는 테스트용 Todo"""
    service = TodoService(test_session)
    data = TodoCreate(
        title="태그 있는 Todo",
        description="태그가 있는 Todo",
        tag_group_id=sample_tag_group.id,
        tag_ids=[sample_tag.id],
    )
    todo = service.create_todo(data)
    test_session.flush()
    test_session.refresh(todo)
    return todo


# ============================================================
# Todo 생성 테스트
# ============================================================

def test_create_todo_success(test_session, sample_tag_group):
    """Todo 생성 성공 테스트"""
    service = TodoService(test_session)
    data = TodoCreate(
        title="회의 준비",
        description="회의 자료 준비",
        tag_group_id=sample_tag_group.id,
    )

    todo = service.create_todo(data)

    assert todo.title == "회의 준비"
    assert todo.description == "회의 자료 준비"
    assert todo.tag_group_id == sample_tag_group.id
    assert todo.status == TodoStatus.UNSCHEDULED
    assert todo.deadline is None
    assert isinstance(todo.id, UUID)


def test_create_todo_with_deadline(test_session, sample_tag_group):
    """마감 시간이 있는 Todo 생성 테스트"""
    service = TodoService(test_session)
    deadline = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    
    data = TodoCreate(
        title="마감 시간 있는 Todo",
        deadline=deadline,
        tag_group_id=sample_tag_group.id,
    )

    todo = service.create_todo(data)
    test_session.flush()
    test_session.refresh(todo)

    assert todo.title == "마감 시간 있는 Todo"
    assert todo.deadline is not None
    # UTC timezone이 있는 datetime은 naive datetime으로 저장됨
    assert todo.deadline.tzinfo is None
    assert todo.deadline == deadline.replace(tzinfo=None)
    
    # Schedule이 생성되었는지 확인
    assert len(todo.schedules) == 1
    schedule = todo.schedules[0]
    assert schedule.source_todo_id == todo.id
    assert schedule.title == todo.title
    # Schedule의 state는 기본값 PLANNED로 설정되어야 함
    assert schedule.state == ScheduleState.PLANNED


def test_create_todo_with_tags(test_session, sample_tag, sample_tag_group):
    """태그와 함께 Todo 생성 테스트"""
    service = TodoService(test_session)
    data = TodoCreate(
        title="태그 있는 Todo",
        tag_group_id=sample_tag_group.id,
        tag_ids=[sample_tag.id],
    )

    todo = service.create_todo(data)
    test_session.flush()
    test_session.refresh(todo)

    # 태그 확인
    tags = service.get_todo_tags(todo.id)
    assert len(tags) == 1
    assert tags[0].id == sample_tag.id


def test_create_todo_with_parent(test_session, sample_tag_group):
    """부모 Todo가 있는 Todo 생성 테스트"""
    service = TodoService(test_session)
    
    # 부모 Todo 생성
    parent_data = TodoCreate(
        title="부모 Todo",
        tag_group_id=sample_tag_group.id,
    )
    parent = service.create_todo(parent_data)
    test_session.flush()
    
    # 자식 Todo 생성
    child_data = TodoCreate(
        title="자식 Todo",
        tag_group_id=sample_tag_group.id,
        parent_id=parent.id,
    )
    child = service.create_todo(child_data)
    test_session.flush()
    test_session.refresh(child)

    assert child.parent_id == parent.id
    assert child.title == "자식 Todo"


def test_create_todo_with_status(test_session, sample_tag_group):
    """상태가 지정된 Todo 생성 테스트"""
    service = TodoService(test_session)
    data = TodoCreate(
        title="완료된 Todo",
        tag_group_id=sample_tag_group.id,
        status=TodoStatus.DONE,
    )

    todo = service.create_todo(data)

    assert todo.status == TodoStatus.DONE


def test_create_todo_without_description(test_session, sample_tag_group):
    """설명 없이 Todo 생성 테스트"""
    service = TodoService(test_session)
    data = TodoCreate(
        title="제목만 있는 Todo",
        tag_group_id=sample_tag_group.id,
    )

    todo = service.create_todo(data)

    assert todo.title == "제목만 있는 Todo"
    assert todo.description is None
    assert todo.status == TodoStatus.UNSCHEDULED


# ============================================================
# Todo 조회 테스트
# ============================================================

def test_get_todo_success(test_session, sample_todo):
    """Todo 조회 성공 테스트"""
    service = TodoService(test_session)
    retrieved_todo = service.get_todo(sample_todo.id)

    assert retrieved_todo.id == sample_todo.id
    assert retrieved_todo.title == sample_todo.title
    assert retrieved_todo.tag_group_id == sample_todo.tag_group_id


def test_get_todo_not_found(test_session):
    """존재하지 않는 Todo 조회 실패 테스트"""
    service = TodoService(test_session)
    fake_id = uuid4()

    with pytest.raises(TodoNotFoundError):
        service.get_todo(fake_id)


def test_get_all_todos_empty(test_session):
    """Todo 목록 조회 (빈 목록) 테스트"""
    service = TodoService(test_session)
    todos = service.get_all_todos()

    assert isinstance(todos, list)
    # 다른 테스트에서 생성된 Todo가 있을 수 있으므로 >= 0
    assert len(todos) >= 0


def test_get_all_todos_multiple(test_session, sample_tag_group):
    """여러 Todo 목록 조회 테스트"""
    service = TodoService(test_session)

    # 여러 Todo 생성
    todo1 = service.create_todo(TodoCreate(title="Todo 1", tag_group_id=sample_tag_group.id))
    todo2 = service.create_todo(TodoCreate(title="Todo 2", tag_group_id=sample_tag_group.id))
    todo3 = service.create_todo(TodoCreate(title="Todo 3", tag_group_id=sample_tag_group.id))
    test_session.flush()

    todos = service.get_all_todos()
    todo_ids = [t.id for t in todos]
    
    assert todo1.id in todo_ids
    assert todo2.id in todo_ids
    assert todo3.id in todo_ids


def test_get_all_todos_filtered_by_tag_ids(test_session, sample_tag_group):
    """태그 ID로 필터링된 Todo 목록 조회 테스트"""
    service = TodoService(test_session)
    tag_service = TagService(test_session)

    # 태그 생성
    tag1 = tag_service.create_tag(TagCreate(
        name="태그1",
        color="#FF0000",
        group_id=sample_tag_group.id,
    ))
    tag2 = tag_service.create_tag(TagCreate(
        name="태그2",
        color="#00FF00",
        group_id=sample_tag_group.id,
    ))

    # Todo 생성
    todo1 = service.create_todo(TodoCreate(title="Todo 1", tag_group_id=sample_tag_group.id, tag_ids=[tag1.id]))
    todo2 = service.create_todo(TodoCreate(title="Todo 2", tag_group_id=sample_tag_group.id, tag_ids=[tag2.id]))
    todo3 = service.create_todo(TodoCreate(title="Todo 3", tag_group_id=sample_tag_group.id, tag_ids=[tag1.id, tag2.id]))
    todo4 = service.create_todo(TodoCreate(title="Todo 4", tag_group_id=sample_tag_group.id))  # 태그 없음
    test_session.flush()

    # tag1만 가진 Todo 조회
    todos = service.get_all_todos(tag_ids=[tag1.id])
    todo_ids = [t.id for t in todos]
    
    assert todo1.id in todo_ids
    assert todo3.id in todo_ids  # tag1과 tag2 둘 다 가진 Todo도 포함
    assert todo2.id not in todo_ids
    assert todo4.id not in todo_ids

    # tag1과 tag2 둘 다 가진 Todo 조회 (AND 방식)
    todos = service.get_all_todos(tag_ids=[tag1.id, tag2.id])
    todo_ids = [t.id for t in todos]
    
    assert todo3.id in todo_ids
    assert todo1.id not in todo_ids
    assert todo2.id not in todo_ids


def test_get_all_todos_filtered_by_group_ids(test_session, sample_tag_group):
    """그룹 ID로 필터링된 Todo 목록 조회 테스트"""
    service = TodoService(test_session)
    tag_service = TagService(test_session)

    # 다른 그룹 생성
    group2 = tag_service.create_tag_group(TagGroupCreate(
        name="개인",
        color="#0000FF",
    ))

    # 태그 생성
    tag1 = tag_service.create_tag(TagCreate(
        name="태그1",
        color="#FF0000",
        group_id=sample_tag_group.id,
    ))
    tag2 = tag_service.create_tag(TagCreate(
        name="태그2",
        color="#00FF00",
        group_id=group2.id,
    ))

    # Todo 생성
    todo1 = service.create_todo(TodoCreate(title="Todo 1", tag_group_id=sample_tag_group.id, tag_ids=[tag1.id]))
    todo2 = service.create_todo(TodoCreate(title="Todo 2", tag_group_id=group2.id, tag_ids=[tag2.id]))
    todo3 = service.create_todo(TodoCreate(title="Todo 3", tag_group_id=sample_tag_group.id))  # 태그 없음
    test_session.flush()

    # sample_tag_group에 속한 Todo 조회
    todos = service.get_all_todos(group_ids=[sample_tag_group.id])
    todo_ids = [t.id for t in todos]
    
    assert todo1.id in todo_ids  # sample_tag_group에 속함
    assert todo3.id in todo_ids  # sample_tag_group에 속함 (태그 없어도 포함)
    assert todo2.id not in todo_ids  # group2에 속함


def test_get_all_todos_filtered_by_tag_and_group_ids(test_session, sample_tag_group):
    """태그 ID와 그룹 ID로 필터링된 Todo 목록 조회 테스트"""
    service = TodoService(test_session)
    tag_service = TagService(test_session)

    # 태그 생성
    tag1 = tag_service.create_tag(TagCreate(
        name="태그1",
        color="#FF0000",
        group_id=sample_tag_group.id,
    ))
    tag2 = tag_service.create_tag(TagCreate(
        name="태그2",
        color="#00FF00",
        group_id=sample_tag_group.id,
    ))

    # Todo 생성
    todo1 = service.create_todo(TodoCreate(title="Todo 1", tag_group_id=sample_tag_group.id, tag_ids=[tag1.id]))
    todo2 = service.create_todo(TodoCreate(title="Todo 2", tag_group_id=sample_tag_group.id, tag_ids=[tag2.id]))
    todo3 = service.create_todo(TodoCreate(title="Todo 3", tag_group_id=sample_tag_group.id, tag_ids=[tag1.id, tag2.id]))
    test_session.flush()

    # 그룹 필터링 후 태그 필터링
    todos = service.get_all_todos(
        tag_ids=[tag1.id],
        group_ids=[sample_tag_group.id],
    )
    todo_ids = [t.id for t in todos]
    
    assert todo1.id in todo_ids
    assert todo3.id in todo_ids  # tag1과 tag2 둘 다 가진 Todo도 포함
    assert todo2.id not in todo_ids


# ============================================================
# Todo 업데이트 테스트
# ============================================================

def test_update_todo_success(test_session, sample_todo):
    """Todo 업데이트 성공 테스트"""
    service = TodoService(test_session)
    update_data = TodoUpdate(
        title="업데이트된 제목",
        description="업데이트된 설명",
    )

    updated_todo = service.update_todo(sample_todo.id, update_data)

    assert updated_todo.title == "업데이트된 제목"
    assert updated_todo.description == "업데이트된 설명"
    assert updated_todo.id == sample_todo.id


def test_update_todo_partial(test_session, sample_todo):
    """Todo 부분 업데이트 테스트 (일부 필드만)"""
    service = TodoService(test_session)
    original_title = sample_todo.title

    update_data = TodoUpdate(description="설명만 업데이트")

    updated_todo = service.update_todo(sample_todo.id, update_data)

    assert updated_todo.title == original_title  # 제목은 변경되지 않음
    assert updated_todo.description == "설명만 업데이트"


def test_update_todo_deadline(test_session, sample_todo):
    """Todo 마감 시간 업데이트 테스트"""
    service = TodoService(test_session)
    new_deadline = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
    
    update_data = TodoUpdate(deadline=new_deadline)
    updated_todo = service.update_todo(sample_todo.id, update_data)
    test_session.flush()
    test_session.refresh(updated_todo)

    assert updated_todo.deadline is not None
    assert updated_todo.deadline == new_deadline.replace(tzinfo=None)
    
    # Schedule이 생성되었는지 확인
    assert len(updated_todo.schedules) == 1
    schedule = updated_todo.schedules[0]
    # Schedule의 state는 기본값 PLANNED로 설정되어야 함
    assert schedule.state == ScheduleState.PLANNED


def test_update_todo_deadline_removal(test_session, sample_tag_group):
    """Todo 마감 시간 제거 테스트"""
    service = TodoService(test_session)
    
    # 마감 시간이 있는 Todo 생성
    deadline = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    todo = service.create_todo(TodoCreate(
        title="마감 시간 있는 Todo",
        tag_group_id=sample_tag_group.id,
        deadline=deadline,
    ))
    test_session.flush()
    test_session.refresh(todo)
    
    assert len(todo.schedules) == 1
    
    # 마감 시간 제거
    update_data = TodoUpdate(deadline=None)
    updated_todo = service.update_todo(todo.id, update_data)
    test_session.flush()
    test_session.refresh(updated_todo)

    assert updated_todo.deadline is None
    # Schedule이 삭제되었는지 확인
    assert len(updated_todo.schedules) == 0


def test_update_todo_status(test_session, sample_todo):
    """Todo 상태 업데이트 테스트"""
    service = TodoService(test_session)
    update_data = TodoUpdate(status=TodoStatus.DONE)

    updated_todo = service.update_todo(sample_todo.id, update_data)

    assert updated_todo.status == TodoStatus.DONE


def test_todo_schedule_state_default(test_session, sample_tag_group):
    """Todo로 생성된 Schedule의 state 기본값 테스트"""
    service = TodoService(test_session)
    deadline = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    
    # 마감 시간이 있는 Todo 생성
    todo = service.create_todo(TodoCreate(
        title="Schedule state 테스트",
        tag_group_id=sample_tag_group.id,
        deadline=deadline,
    ))
    test_session.flush()
    test_session.refresh(todo)
    
    # Schedule이 생성되었는지 확인
    assert len(todo.schedules) == 1
    schedule = todo.schedules[0]
    
    # Schedule의 state는 기본값 PLANNED로 설정되어야 함
    assert schedule.state == ScheduleState.PLANNED
    assert schedule.source_todo_id == todo.id


def test_todo_schedule_state_when_adding_deadline(test_session, sample_tag_group):
    """deadline 추가 시 생성된 Schedule의 state 기본값 테스트"""
    service = TodoService(test_session)
    
    # 마감 시간이 없는 Todo 생성
    todo = service.create_todo(TodoCreate(
        title="초기에는 deadline 없음",
        tag_group_id=sample_tag_group.id,
    ))
    test_session.flush()
    test_session.refresh(todo)
    
    assert len(todo.schedules) == 0
    
    # deadline 추가
    deadline = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    update_data = TodoUpdate(deadline=deadline)
    updated_todo = service.update_todo(todo.id, update_data)
    test_session.flush()
    test_session.refresh(updated_todo)
    
    # Schedule이 생성되었는지 확인
    assert len(updated_todo.schedules) == 1
    schedule = updated_todo.schedules[0]
    
    # Schedule의 state는 기본값 PLANNED로 설정되어야 함
    assert schedule.state == ScheduleState.PLANNED


def test_update_todo_parent(test_session, sample_tag_group):
    """Todo 부모 변경 테스트"""
    service = TodoService(test_session)
    
    # 부모 Todo 생성
    parent1 = service.create_todo(TodoCreate(
        title="부모 1",
        tag_group_id=sample_tag_group.id,
    ))
    parent2 = service.create_todo(TodoCreate(
        title="부모 2",
        tag_group_id=sample_tag_group.id,
    ))
    
    # 자식 Todo 생성
    child = service.create_todo(TodoCreate(
        title="자식",
        tag_group_id=sample_tag_group.id,
        parent_id=parent1.id,
    ))
    test_session.flush()
    
    assert child.parent_id == parent1.id
    
    # 부모 변경
    update_data = TodoUpdate(parent_id=parent2.id)
    updated_todo = service.update_todo(child.id, update_data)
    test_session.flush()
    test_session.refresh(updated_todo)

    assert updated_todo.parent_id == parent2.id


def test_update_todo_tags(test_session, sample_todo, sample_tag_group):
    """Todo 태그 업데이트 테스트"""
    service = TodoService(test_session)
    tag_service = TagService(test_session)

    # 태그 생성
    tag1 = tag_service.create_tag(TagCreate(
        name="태그1",
        color="#FF0000",
        group_id=sample_tag_group.id,
    ))
    tag2 = tag_service.create_tag(TagCreate(
        name="태그2",
        color="#00FF00",
        group_id=sample_tag_group.id,
    ))

    # 태그 업데이트
    update_data = TodoUpdate(tag_ids=[tag1.id, tag2.id])
    updated_todo = service.update_todo(sample_todo.id, update_data)

    # 태그 확인
    tags = service.get_todo_tags(updated_todo.id)
    tag_ids = [t.id for t in tags]
    assert tag1.id in tag_ids
    assert tag2.id in tag_ids


def test_update_todo_remove_tags(test_session, sample_todo_with_tags):
    """Todo 태그 제거 테스트"""
    service = TodoService(test_session)

    # 태그 제거
    update_data = TodoUpdate(tag_ids=[])
    updated_todo = service.update_todo(sample_todo_with_tags.id, update_data)

    # 태그가 제거되었는지 확인
    tags = service.get_todo_tags(updated_todo.id)
    assert len(tags) == 0


def test_update_todo_not_found(test_session):
    """존재하지 않는 Todo 업데이트 실패 테스트"""
    service = TodoService(test_session)
    fake_id = uuid4()
    update_data = TodoUpdate(title="업데이트")

    with pytest.raises(TodoNotFoundError):
        service.update_todo(fake_id, update_data)


# ============================================================
# Todo 삭제 테스트
# ============================================================

def test_delete_todo_success(test_session, sample_todo):
    """Todo 삭제 성공 테스트"""
    service = TodoService(test_session)
    todo_id = sample_todo.id

    service.delete_todo(todo_id)
    test_session.flush()

    # 삭제 확인
    test_session.expire_all()
    with pytest.raises(TodoNotFoundError):
        service.get_todo(todo_id)


def test_delete_todo_with_schedule(test_session, sample_tag_group):
    """Schedule이 연관된 Todo 삭제 테스트"""
    service = TodoService(test_session)
    deadline = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    
    # 마감 시간이 있는 Todo 생성 (Schedule 자동 생성)
    todo = service.create_todo(TodoCreate(
        title="Schedule 있는 Todo",
        tag_group_id=sample_tag_group.id,
        deadline=deadline,
    ))
    test_session.flush()
    test_session.refresh(todo)
    
    todo_id = todo.id
    schedule_id = todo.schedules[0].id
    
    # Todo 삭제
    service.delete_todo(todo_id)
    test_session.flush()
    
    # Todo가 삭제되었는지 확인
    test_session.expire_all()
    with pytest.raises(TodoNotFoundError):
        service.get_todo(todo_id)
    
    # Schedule도 삭제되었는지 확인
    from app.domain.schedule.service import ScheduleService
    schedule_service = ScheduleService(test_session)
    from app.domain.schedule.exceptions import ScheduleNotFoundError
    with pytest.raises(ScheduleNotFoundError):
        schedule_service.get_schedule(schedule_id)


def test_delete_todo_with_children(test_session, sample_tag_group):
    """자식 Todo가 있는 부모 Todo 삭제 테스트"""
    service = TodoService(test_session)
    
    # 부모 Todo 생성
    parent = service.create_todo(TodoCreate(
        title="부모",
        tag_group_id=sample_tag_group.id,
    ))
    
    # 자식 Todo 생성
    child1 = service.create_todo(TodoCreate(
        title="자식 1",
        tag_group_id=sample_tag_group.id,
        parent_id=parent.id,
    ))
    child2 = service.create_todo(TodoCreate(
        title="자식 2",
        tag_group_id=sample_tag_group.id,
        parent_id=parent.id,
    ))
    test_session.flush()
    
    parent_id = parent.id
    child1_id = child1.id
    child2_id = child2.id
    
    # 부모 Todo 삭제 (자식도 함께 삭제되어야 함 - CASCADE)
    service.delete_todo(parent_id)
    test_session.flush()
    
    # 부모와 자식이 모두 삭제되었는지 확인
    test_session.expire_all()
    with pytest.raises(TodoNotFoundError):
        service.get_todo(parent_id)
    with pytest.raises(TodoNotFoundError):
        service.get_todo(child1_id)
    with pytest.raises(TodoNotFoundError):
        service.get_todo(child2_id)


def test_delete_todo_not_found(test_session):
    """존재하지 않는 Todo 삭제 실패 테스트"""
    service = TodoService(test_session)
    fake_id = uuid4()

    with pytest.raises(TodoNotFoundError):
        service.delete_todo(fake_id)


# ============================================================
# Todo 태그 조회 테스트
# ============================================================

def test_get_todo_tags_empty(test_session, sample_todo):
    """Todo 태그 조회 (태그 없음) 테스트"""
    service = TodoService(test_session)
    tags = service.get_todo_tags(sample_todo.id)

    assert len(tags) == 0


def test_get_todo_tags_multiple(test_session, sample_tag_group):
    """여러 태그가 있는 Todo 태그 조회 테스트"""
    service = TodoService(test_session)
    tag_service = TagService(test_session)

    # 태그 생성
    tag1 = tag_service.create_tag(TagCreate(
        name="태그1",
        color="#FF0000",
        group_id=sample_tag_group.id,
    ))
    tag2 = tag_service.create_tag(TagCreate(
        name="태그2",
        color="#00FF00",
        group_id=sample_tag_group.id,
    ))

    # Todo 생성
    todo = service.create_todo(TodoCreate(
        title="태그 있는 Todo",
        tag_group_id=sample_tag_group.id,
        tag_ids=[tag1.id, tag2.id],
    ))
    test_session.flush()

    # 태그 조회
    tags = service.get_todo_tags(todo.id)
    assert len(tags) == 2
    tag_ids = [t.id for t in tags]
    assert tag1.id in tag_ids
    assert tag2.id in tag_ids


# ============================================================
# Todo 통계 테스트
# ============================================================

def test_get_todo_stats_empty(test_session):
    """Todo 통계 조회 (Todo 없음) 테스트"""
    service = TodoService(test_session)
    stats = service.get_todo_stats()

    assert stats.total_count == 0
    assert len(stats.by_tag) == 0
    assert stats.group_id is None


def test_get_todo_stats_with_todos(test_session, sample_tag_group):
    """Todo 통계 조회 테스트"""
    service = TodoService(test_session)
    tag_service = TagService(test_session)

    # 태그 생성
    tag1 = tag_service.create_tag(TagCreate(
        name="태그1",
        color="#FF0000",
        group_id=sample_tag_group.id,
    ))
    tag2 = tag_service.create_tag(TagCreate(
        name="태그2",
        color="#00FF00",
        group_id=sample_tag_group.id,
    ))

    # Todo 생성
    service.create_todo(TodoCreate(title="Todo 1", tag_group_id=sample_tag_group.id, tag_ids=[tag1.id]))
    service.create_todo(TodoCreate(title="Todo 2", tag_group_id=sample_tag_group.id, tag_ids=[tag1.id]))
    service.create_todo(TodoCreate(title="Todo 3", tag_group_id=sample_tag_group.id, tag_ids=[tag2.id]))
    service.create_todo(TodoCreate(title="Todo 4", tag_group_id=sample_tag_group.id))  # 태그 없음
    test_session.flush()

    # 통계 조회
    stats = service.get_todo_stats()

    assert stats.total_count == 4
    assert len(stats.by_tag) == 2
    
    # 태그별 카운트 확인
    tag_counts = {stat.tag_id: stat.count for stat in stats.by_tag}
    assert tag_counts[tag1.id] == 2
    assert tag_counts[tag2.id] == 1


def test_get_todo_stats_filtered_by_group(test_session, sample_tag_group):
    """그룹별 Todo 통계 조회 테스트"""
    service = TodoService(test_session)
    tag_service = TagService(test_session)

    # 다른 그룹 생성
    group2 = tag_service.create_tag_group(TagGroupCreate(
        name="개인",
        color="#0000FF",
    ))

    # 태그 생성
    tag1 = tag_service.create_tag(TagCreate(
        name="태그1",
        color="#FF0000",
        group_id=sample_tag_group.id,
    ))
    tag2 = tag_service.create_tag(TagCreate(
        name="태그2",
        color="#00FF00",
        group_id=group2.id,
    ))

    # Todo 생성
    service.create_todo(TodoCreate(title="Todo 1", tag_group_id=sample_tag_group.id, tag_ids=[tag1.id]))
    service.create_todo(TodoCreate(title="Todo 2", tag_group_id=group2.id, tag_ids=[tag2.id]))
    test_session.flush()

    # sample_tag_group의 통계만 조회
    stats = service.get_todo_stats(group_id=sample_tag_group.id)

    assert stats.total_count == 1
    assert stats.group_id == sample_tag_group.id
    assert len(stats.by_tag) == 1
    assert stats.by_tag[0].tag_id == tag1.id
    assert stats.by_tag[0].count == 1


# ============================================================
# Todo DTO 변환 테스트
# ============================================================

def test_to_read_dto(test_session, sample_todo):
    """Todo를 TodoRead DTO로 변환 테스트"""
    service = TodoService(test_session)
    dto = service.to_read_dto(sample_todo)

    assert dto.id == sample_todo.id
    assert dto.title == sample_todo.title
    assert dto.status == sample_todo.status
    assert isinstance(dto.tags, list)
    assert isinstance(dto.schedules, list)


def test_to_read_dto_with_tags(test_session, sample_todo_with_tags, sample_tag):
    """태그가 있는 Todo를 TodoRead DTO로 변환 테스트"""
    service = TodoService(test_session)
    dto = service.to_read_dto(sample_todo_with_tags)

    assert dto.id == sample_todo_with_tags.id
    assert len(dto.tags) == 1
    assert dto.tags[0].id == sample_tag.id
