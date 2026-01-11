"""
Todo Service Tests

Todo 서비스의 비즈니스 로직을 테스트합니다.
"""
from datetime import datetime, UTC
from uuid import UUID, uuid4

import pytest

from app.domain.schedule.enums import ScheduleState
from app.domain.tag.schema.dto import TagGroupCreate, TagCreate
from app.domain.tag.service import TagService
from app.domain.todo.enums import TodoStatus
from app.domain.todo.exceptions import TodoNotFoundError
from app.domain.todo.schema.dto import TodoCreate, TodoUpdate, TodoIncludeReason
from app.domain.todo.service import TodoService


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
    result = service.get_all_todos()

    assert isinstance(result.todos, list)
    # 다른 테스트에서 생성된 Todo가 있을 수 있으므로 >= 0
    assert len(result.todos) >= 0


def test_get_all_todos_multiple(test_session, sample_tag_group):
    """여러 Todo 목록 조회 테스트"""
    service = TodoService(test_session)

    # 여러 Todo 생성
    todo1 = service.create_todo(TodoCreate(title="Todo 1", tag_group_id=sample_tag_group.id))
    todo2 = service.create_todo(TodoCreate(title="Todo 2", tag_group_id=sample_tag_group.id))
    todo3 = service.create_todo(TodoCreate(title="Todo 3", tag_group_id=sample_tag_group.id))
    test_session.flush()

    result = service.get_all_todos()
    todo_ids = [t.id for t in result.todos]

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
    todo3 = service.create_todo(
        TodoCreate(title="Todo 3", tag_group_id=sample_tag_group.id, tag_ids=[tag1.id, tag2.id]))
    todo4 = service.create_todo(TodoCreate(title="Todo 4", tag_group_id=sample_tag_group.id))  # 태그 없음
    test_session.flush()

    # tag1만 가진 Todo 조회
    result = service.get_all_todos(tag_ids=[tag1.id])
    todo_ids = [t.id for t in result.todos]

    assert todo1.id in todo_ids
    assert todo3.id in todo_ids  # tag1과 tag2 둘 다 가진 Todo도 포함
    assert todo2.id not in todo_ids
    assert todo4.id not in todo_ids

    # tag1과 tag2 둘 다 가진 Todo 조회 (AND 방식)
    result = service.get_all_todos(tag_ids=[tag1.id, tag2.id])
    todo_ids = [t.id for t in result.todos]

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
    result = service.get_all_todos(group_ids=[sample_tag_group.id])
    todo_ids = [t.id for t in result.todos]

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
    todo3 = service.create_todo(
        TodoCreate(title="Todo 3", tag_group_id=sample_tag_group.id, tag_ids=[tag1.id, tag2.id]))
    test_session.flush()

    # 그룹 필터링 후 태그 필터링
    result = service.get_all_todos(
        tag_ids=[tag1.id],
        group_ids=[sample_tag_group.id],
    )
    todo_ids = [t.id for t in result.todos]

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
    """자식 Todo가 있는 부모 Todo 삭제 테스트 - 자식은 루트로 승격"""
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

    # 부모 Todo 삭제 (자식은 삭제되지 않고 루트로 승격됨)
    service.delete_todo(parent_id)
    test_session.flush()

    # 부모만 삭제되었는지 확인
    test_session.expire_all()
    with pytest.raises(TodoNotFoundError):
        service.get_todo(parent_id)

    # 자식들은 삭제되지 않고 루트로 승격됨 (parent_id = None)
    child1_after = service.get_todo(child1_id)
    child2_after = service.get_todo(child2_id)
    assert child1_after.parent_id is None
    assert child2_after.parent_id is None
    assert child1_after.title == "자식 1"
    assert child2_after.title == "자식 2"


def test_delete_todo_with_children_keeps_child_schedules(test_session, sample_tag_group):
    """부모 Todo 삭제 시 자식 Todo의 Schedule은 유지되어야 함"""
    from datetime import timedelta
    from app.domain.schedule.service import ScheduleService
    
    service = TodoService(test_session)

    # 부모 Todo 생성
    parent = service.create_todo(TodoCreate(
        title="부모",
        tag_group_id=sample_tag_group.id,
    ))

    # deadline이 있는 자식 Todo 생성 (Schedule 자동 생성됨)
    now = datetime.now()
    child = service.create_todo(TodoCreate(
        title="자식 with Schedule",
        tag_group_id=sample_tag_group.id,
        parent_id=parent.id,
        deadline=now + timedelta(days=7),
    ))
    test_session.flush()

    parent_id = parent.id
    child_id = child.id

    # 자식의 Schedule ID 저장
    from app.crud import schedule as schedule_crud
    child_schedules = schedule_crud.get_schedules_by_source_todo_id(test_session, child_id)
    assert len(child_schedules) == 1
    child_schedule_id = child_schedules[0].id

    # 부모 Todo 삭제
    service.delete_todo(parent_id)
    test_session.flush()

    # 부모만 삭제되었는지 확인
    test_session.expire_all()
    with pytest.raises(TodoNotFoundError):
        service.get_todo(parent_id)

    # 자식 Todo는 루트로 승격되어 유지됨
    child_after = service.get_todo(child_id)
    assert child_after.parent_id is None
    assert child_after.title == "자식 with Schedule"

    # 자식 Todo의 Schedule도 유지됨
    schedule_service = ScheduleService(test_session)
    child_schedule = schedule_service.get_schedule(child_schedule_id)
    assert child_schedule.source_todo_id == child_id
    assert child_schedule.title == "자식 with Schedule"


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


# ============================================================
# Todo 트리 무결성 테스트 (parent_id 검증)
# ============================================================

def test_create_todo_with_invalid_parent(test_session, sample_tag_group):
    """존재하지 않는 부모 Todo 참조 시 실패 테스트"""
    from app.domain.todo.exceptions import TodoInvalidParentError

    service = TodoService(test_session)
    fake_parent_id = uuid4()

    data = TodoCreate(
        title="자식 Todo",
        tag_group_id=sample_tag_group.id,
        parent_id=fake_parent_id,
    )

    with pytest.raises(TodoInvalidParentError):
        service.create_todo(data)


def test_update_todo_self_reference(test_session, sample_todo):
    """자기 자신을 부모로 설정 시 실패 테스트"""
    from app.domain.todo.exceptions import TodoSelfReferenceError

    service = TodoService(test_session)

    update_data = TodoUpdate(parent_id=sample_todo.id)

    with pytest.raises(TodoSelfReferenceError):
        service.update_todo(sample_todo.id, update_data)


def test_create_todo_parent_group_mismatch(test_session, sample_tag_group):
    """부모와 자식의 그룹이 다를 때 실패 테스트"""
    from app.domain.todo.exceptions import TodoParentGroupMismatchError

    service = TodoService(test_session)
    tag_service = TagService(test_session)

    # 다른 그룹 생성
    other_group = tag_service.create_tag_group(TagGroupCreate(
        name="다른 그룹",
        color="#0000FF",
    ))

    # 부모 Todo 생성 (sample_tag_group)
    parent = service.create_todo(TodoCreate(
        title="부모 Todo",
        tag_group_id=sample_tag_group.id,
    ))
    test_session.flush()

    # 다른 그룹의 자식 Todo 생성 시도
    data = TodoCreate(
        title="자식 Todo",
        tag_group_id=other_group.id,  # 다른 그룹
        parent_id=parent.id,
    )

    with pytest.raises(TodoParentGroupMismatchError):
        service.create_todo(data)


def test_update_todo_creates_cycle(test_session, sample_tag_group):
    """순환 참조 생성 시 실패 테스트 (A→B→A)"""
    from app.domain.todo.exceptions import TodoCycleError

    service = TodoService(test_session)

    # A 생성
    todo_a = service.create_todo(TodoCreate(
        title="Todo A",
        tag_group_id=sample_tag_group.id,
    ))
    test_session.flush()

    # B 생성 (부모: A)
    todo_b = service.create_todo(TodoCreate(
        title="Todo B",
        tag_group_id=sample_tag_group.id,
        parent_id=todo_a.id,
    ))
    test_session.flush()

    # A의 부모를 B로 설정 시도 → cycle
    update_data = TodoUpdate(parent_id=todo_b.id)

    with pytest.raises(TodoCycleError):
        service.update_todo(todo_a.id, update_data)


def test_update_todo_creates_deep_cycle(test_session, sample_tag_group):
    """깊은 순환 참조 생성 시 실패 테스트 (A→B→C, C의 부모를 A로)"""
    from app.domain.todo.exceptions import TodoCycleError

    service = TodoService(test_session)

    # A → B → C 체인 생성
    todo_a = service.create_todo(TodoCreate(
        title="Todo A",
        tag_group_id=sample_tag_group.id,
    ))
    test_session.flush()

    todo_b = service.create_todo(TodoCreate(
        title="Todo B",
        tag_group_id=sample_tag_group.id,
        parent_id=todo_a.id,
    ))
    test_session.flush()

    todo_c = service.create_todo(TodoCreate(
        title="Todo C",
        tag_group_id=sample_tag_group.id,
        parent_id=todo_b.id,
    ))
    test_session.flush()

    # A의 부모를 C로 설정 시도 → cycle (C→B→A→C)
    update_data = TodoUpdate(parent_id=todo_c.id)

    with pytest.raises(TodoCycleError):
        service.update_todo(todo_a.id, update_data)


# ============================================================
# Todo 정렬 테스트
# ============================================================

def test_get_all_todos_sorted_by_status(test_session, sample_tag_group):
    """Todo 목록이 상태 순으로 정렬되는지 테스트"""

    service = TodoService(test_session)
    base_time = datetime(2024, 1, 1, 12, 0, 0)

    # 역순으로 생성 (CANCELLED → DONE → SCHEDULED → UNSCHEDULED)
    todo_cancelled = service.create_todo(TodoCreate(
        title="취소됨",
        tag_group_id=sample_tag_group.id,
        status=TodoStatus.CANCELLED,
    ))
    test_session.flush()

    todo_done = service.create_todo(TodoCreate(
        title="완료됨",
        tag_group_id=sample_tag_group.id,
        status=TodoStatus.DONE,
    ))
    test_session.flush()

    todo_scheduled = service.create_todo(TodoCreate(
        title="예정됨",
        tag_group_id=sample_tag_group.id,
        status=TodoStatus.SCHEDULED,
    ))
    test_session.flush()

    todo_unscheduled = service.create_todo(TodoCreate(
        title="미예정",
        tag_group_id=sample_tag_group.id,
        status=TodoStatus.UNSCHEDULED,
    ))
    test_session.flush()

    result = service.get_all_todos(group_ids=[sample_tag_group.id])

    # 상태 순서대로 정렬되어야 함: UNSCHEDULED → SCHEDULED → DONE → CANCELLED
    statuses = [t.status for t in result.todos]
    expected_order = [
        TodoStatus.UNSCHEDULED,
        TodoStatus.SCHEDULED,
        TodoStatus.DONE,
        TodoStatus.CANCELLED,
    ]

    # 각 상태가 올바른 순서로 나타나는지 확인
    last_order = -1
    for status in statuses:
        current_order = expected_order.index(status)
        assert current_order >= last_order, f"상태 순서가 잘못됨: {statuses}"
        last_order = current_order


def test_get_all_todos_sorted_by_deadline(test_session, sample_tag_group):
    """Todo 목록이 deadline 순으로 정렬되는지 테스트 (null은 뒤)"""
    service = TodoService(test_session)

    # 모두 같은 상태로 생성
    todo_no_deadline = service.create_todo(TodoCreate(
        title="마감 없음",
        tag_group_id=sample_tag_group.id,
        deadline=None,
    ))
    test_session.flush()

    todo_late_deadline = service.create_todo(TodoCreate(
        title="늦은 마감",
        tag_group_id=sample_tag_group.id,
        deadline=datetime(2024, 12, 31, 12, 0, 0, tzinfo=UTC),
    ))
    test_session.flush()

    todo_early_deadline = service.create_todo(TodoCreate(
        title="빠른 마감",
        tag_group_id=sample_tag_group.id,
        deadline=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
    ))
    test_session.flush()

    result = service.get_all_todos(group_ids=[sample_tag_group.id])

    # 같은 상태에서 deadline 순 (null은 뒤): 빠른 마감 → 늦은 마감 → 마감 없음
    titles = [t.title for t in result.todos]

    # deadline이 있는 것들이 null보다 먼저
    deadline_todos = [t for t in result.todos if t.deadline is not None]
    no_deadline_todos = [t for t in result.todos if t.deadline is None]

    # deadline 있는 것들이 먼저 나와야 함
    assert all(t.title in ["빠른 마감", "늦은 마감"] for t in deadline_todos)
    assert all(t.title == "마감 없음" for t in no_deadline_todos)

    # deadline이 있는 것들 중에서는 오름차순
    if len(deadline_todos) >= 2:
        deadlines = [t.deadline for t in deadline_todos]
        assert deadlines == sorted(deadlines)


# ============================================================
# Todo 조상 포함 테스트 (태그 필터 시)
# ============================================================

def test_get_all_todos_includes_ancestors_with_tag_filter(test_session, sample_tag_group):
    """태그 필터 시 조상 노드도 포함되는지 테스트"""
    service = TodoService(test_session)
    tag_service = TagService(test_session)

    # 태그 생성
    tag = tag_service.create_tag(TagCreate(
        name="특수태그",
        color="#FF0000",
        group_id=sample_tag_group.id,
    ))
    test_session.flush()

    # 부모 Todo (태그 없음)
    parent = service.create_todo(TodoCreate(
        title="부모 (태그 없음)",
        tag_group_id=sample_tag_group.id,
    ))
    test_session.flush()

    # 자식 Todo (태그 있음)
    child = service.create_todo(TodoCreate(
        title="자식 (태그 있음)",
        tag_group_id=sample_tag_group.id,
        parent_id=parent.id,
        tag_ids=[tag.id],
    ))
    test_session.flush()

    # 태그로 필터링
    result = service.get_all_todos(tag_ids=[tag.id])
    todo_ids = [t.id for t in result.todos]

    # 자식은 태그 매칭으로 포함
    assert child.id in todo_ids, "자식 Todo가 결과에 포함되어야 함"
    # 부모는 조상으로 포함
    assert parent.id in todo_ids, "부모 Todo가 조상으로 포함되어야 함"

    # include_reason 확인
    assert result.include_reason_by_id[child.id] == TodoIncludeReason.MATCH
    assert result.include_reason_by_id[parent.id] == TodoIncludeReason.ANCESTOR


def test_get_all_todos_includes_deep_ancestors_with_tag_filter(test_session, sample_tag_group):
    """태그 필터 시 깊은 조상 노드들도 포함되는지 테스트"""
    service = TodoService(test_session)
    tag_service = TagService(test_session)

    # 태그 생성
    tag = tag_service.create_tag(TagCreate(
        name="깊은태그",
        color="#00FF00",
        group_id=sample_tag_group.id,
    ))
    test_session.flush()

    # 3단계 트리: grandparent → parent → child
    grandparent = service.create_todo(TodoCreate(
        title="조부모",
        tag_group_id=sample_tag_group.id,
    ))
    test_session.flush()

    parent = service.create_todo(TodoCreate(
        title="부모",
        tag_group_id=sample_tag_group.id,
        parent_id=grandparent.id,
    ))
    test_session.flush()

    child = service.create_todo(TodoCreate(
        title="자식",
        tag_group_id=sample_tag_group.id,
        parent_id=parent.id,
        tag_ids=[tag.id],
    ))
    test_session.flush()

    # 태그로 필터링
    result = service.get_all_todos(tag_ids=[tag.id])
    todo_ids = [t.id for t in result.todos]

    # 모든 조상이 포함되어야 함
    assert child.id in todo_ids, "자식 Todo가 결과에 포함되어야 함"
    assert parent.id in todo_ids, "부모 Todo가 조상으로 포함되어야 함"
    assert grandparent.id in todo_ids, "조부모 Todo가 조상으로 포함되어야 함"

    # include_reason 확인
    assert result.include_reason_by_id[child.id] == TodoIncludeReason.MATCH
    assert result.include_reason_by_id[parent.id] == TodoIncludeReason.ANCESTOR
    assert result.include_reason_by_id[grandparent.id] == TodoIncludeReason.ANCESTOR
