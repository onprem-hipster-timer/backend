"""
Todo CRUD / DTO timezone 처리 회귀 테스트

테스트 목적:
- 세계 일정 서비스 기준으로 Todo.deadline의 timezone 처리를 검증한다.
- 해외 출장 등으로 클라이언트가 자기 타임존이 붙은 aware datetime을 보낼 수 있다.
- DB는 naive UTC(TIMESTAMP WITHOUT TIME ZONE)로 저장하므로,
  aware datetime은 UTC로 변환된 뒤 naive로 저장되어야 한다. (#41 동일 버그 클래스)

검증 범위:
1. DTO 검증 단계: TodoCreate/TodoUpdate.deadline이 aware -> UTC naive로 변환된다.
2. CRUD 저장 단계: crud.create_todo / crud.update_todo가 naive UTC deadline을 저장한다.
3. 응답 단계: TodoRead.to_timezone이 naive UTC를 요청 타임존 aware로 변환한다.

중요:
- 이 테스트는 SQLite보다 PostgreSQL 테스트 DB에서 실행하는 것이 정확하다.
- SQLite는 timezone 타입을 엄격히 검증하지 않기 때문에 운영 장애를 재현하지 못할 수 있다.
"""

from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from pydantic.experimental.missing_sentinel import MISSING

from app.crud.todo import create_todo, update_todo
from app.domain.tag.schema.dto import TagGroupCreate
from app.domain.tag.service import TagService
from app.domain.todo.enums import TodoStatus
from app.domain.todo.schema.dto import TodoCreate, TodoRead, TodoUpdate
from app.models.todo import Todo

KST = ZoneInfo("Asia/Seoul")


@pytest.fixture
def tag_group(test_session, test_user):
    """Todo의 필수 FK(tag_group_id)를 위한 태그 그룹"""
    service = TagService(test_session, test_user)
    return service.create_tag_group(
        TagGroupCreate(
            name="업무",
            color="#FF5733",
            description="업무 관련 태그 그룹",
        )
    )


def _assert_utc_naive(value: datetime | None) -> None:
    """저장/변환된 datetime이 timezone-naive UTC인지 검증한다."""
    assert value is not None
    assert isinstance(value, datetime)
    assert value.tzinfo is None


# ============ 1. DTO 검증 단계 ============


def test_todo_create_dto_converts_aware_kst_deadline_to_naive_utc():
    """
    목적 객체:
    - TodoCreate.ensure_utc_naive_datetime

    검증:
    - KST aware deadline이 UTC naive로 변환된다.
      (KST 2024-01-01 09:00 -> UTC 2024-01-01 00:00)
    """
    dto = TodoCreate(
        title="마감 있는 Todo",
        tag_group_id=uuid4(),
        deadline=datetime(2024, 1, 1, 9, 0, 0, tzinfo=KST),
    )

    _assert_utc_naive(dto.deadline)
    assert dto.deadline == datetime(2024, 1, 1, 0, 0, 0)


def test_todo_create_dto_accepts_naive_deadline_as_utc():
    """
    검증:
    - naive deadline은 UTC로 가정하여 그대로 유지된다.
    """
    dto = TodoCreate(
        title="마감 있는 Todo",
        tag_group_id=uuid4(),
        deadline=datetime(2024, 1, 1, 0, 0, 0),
    )

    _assert_utc_naive(dto.deadline)
    assert dto.deadline == datetime(2024, 1, 1, 0, 0, 0)


def test_todo_create_dto_allows_none_deadline():
    """
    검증:
    - deadline이 없으면 None을 유지한다.
    """
    dto = TodoCreate(
        title="마감 없는 Todo",
        tag_group_id=uuid4(),
    )

    assert dto.deadline is None


def test_todo_update_dto_converts_aware_deadline_to_naive_utc():
    """
    목적 객체:
    - TodoUpdate.ensure_utc_naive_datetime

    검증:
    - KST aware deadline이 UTC naive로 변환된다.
      (KST 2024-03-01 09:00 -> UTC 2024-03-01 00:00)
    """
    dto = TodoUpdate(deadline=datetime(2024, 3, 1, 9, 0, 0, tzinfo=KST))

    _assert_utc_naive(dto.deadline)
    assert dto.deadline == datetime(2024, 3, 1, 0, 0, 0)


def test_todo_update_dto_omitted_deadline_stays_missing():
    """
    검증:
    - deadline을 지정하지 않으면 MISSING 센티넬을 유지한다.
    - (validator가 MISSING 기본값에는 적용되지 않아야 한다.)
    """
    dto = TodoUpdate(title="제목만 변경")

    assert dto.deadline is MISSING


# ============ 2. CRUD 저장 단계 ============


def test_create_todo_persists_naive_utc_deadline(test_session, test_user, tag_group):
    """
    목적 객체:
    - crud.create_todo()

    검증:
    - DTO 검증을 거친 deadline(naive UTC)이 그대로 DB에 저장된다.
    - 저장된 deadline은 timezone-naive UTC이다.
    """
    create = TodoCreate(
        title="마감 있는 Todo",
        tag_group_id=tag_group.id,
        deadline=datetime(2024, 1, 1, 9, 0, 0, tzinfo=KST),  # KST -> UTC 00:00
    )

    todo = Todo(
        owner_id=test_user.sub,
        title=create.title,
        tag_group_id=create.tag_group_id,
        deadline=create.deadline,
        status=TodoStatus.UNSCHEDULED,
    )

    saved = create_todo(test_session, todo)

    _assert_utc_naive(saved.deadline)
    assert saved.deadline == datetime(2024, 1, 1, 0, 0, 0)
    _assert_utc_naive(saved.created_at)
    _assert_utc_naive(saved.updated_at)


def test_update_todo_persists_naive_utc_deadline(test_session, test_user, tag_group):
    """
    목적 객체:
    - crud.update_todo()

    검증:
    - aware deadline으로 업데이트해도 DTO 검증을 거쳐 naive UTC로 저장된다.
    """
    todo = create_todo(
        test_session,
        Todo(
            owner_id=test_user.sub,
            title="마감 추가 예정",
            tag_group_id=tag_group.id,
            status=TodoStatus.UNSCHEDULED,
        ),
    )

    update = TodoUpdate(deadline=datetime(2024, 3, 1, 9, 0, 0, tzinfo=KST))  # KST -> UTC 00:00

    updated = update_todo(test_session, todo, update)

    _assert_utc_naive(updated.deadline)
    assert updated.deadline == datetime(2024, 3, 1, 0, 0, 0)


# ============ 3. 응답 단계 (출력 타임존 변환) ============


def test_todo_read_to_timezone_converts_deadline_and_created_at():
    """
    목적 객체:
    - TodoRead.to_timezone()

    검증:
    - naive UTC로 저장된 deadline/created_at이 요청 타임존(KST) aware로 변환된다.
      (UTC 2024-01-01 00:00 -> KST 2024-01-01 09:00, offset +09:00)
    """
    todo_read = TodoRead(
        id=uuid4(),
        title="마감 있는 Todo",
        tag_group_id=uuid4(),
        status=TodoStatus.UNSCHEDULED,
        deadline=datetime(2024, 1, 1, 0, 0, 0),
        created_at=datetime(2024, 1, 1, 0, 0, 0),
    )

    converted = todo_read.to_timezone(KST)

    assert converted.deadline.tzinfo is not None
    assert converted.deadline.utcoffset() == timedelta(hours=9)
    assert converted.deadline.hour == 9
    assert converted.created_at.utcoffset() == timedelta(hours=9)


def test_todo_read_to_timezone_none_returns_self():
    """
    검증:
    - tz가 None이면 변환 없이 동일 인스턴스를 반환한다 (UTC naive 유지).
    """
    todo_read = TodoRead(
        id=uuid4(),
        title="마감 있는 Todo",
        tag_group_id=uuid4(),
        status=TodoStatus.UNSCHEDULED,
        deadline=datetime(2024, 1, 1, 0, 0, 0),
        created_at=datetime(2024, 1, 1, 0, 0, 0),
    )

    result = todo_read.to_timezone(None)

    assert result is todo_read
    _assert_utc_naive(result.deadline)
