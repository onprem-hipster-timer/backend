"""
Schedule→Todo 역전파 테스트 (Phase B — #55 잔여, #44)

source of truth 규칙 (domain-events.ko.md §5):
- Todo.deadline이 원본, Schedule.start_time은 투영 — 단 `source_todo_id`가
  있는(=Todo가 만든) Schedule의 시간 변경은 Todo로 역투영된다
- origin이 TODO인 변경은 재전파하지 않는다 (왕복 차단)
- 반복 일정이 된 source-linked Schedule은 역투영하지 않는다
  (시점 마감의 투영이 아니게 되므로 — 이 테스트로 결정 고정)
- 투영 일정 삭제 시 Todo와 deadline은 유지, status만 UNSCHEDULED
  (#55 "Schedule 삭제 정책(기본: 유지) — 테스트명으로 못박기")
"""
from datetime import UTC, datetime, timedelta

import pytest

from app.crud import schedule as schedule_crud
from app.domain.schedule.schema.dto import CreateTodoOptions, ScheduleCreate, ScheduleUpdate
from app.domain.schedule.service import ScheduleService
from app.domain.todo.enums import TodoStatus
from app.domain.todo.schema.dto import TodoCreate
from app.domain.todo.service import TodoService

DEADLINE = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)
NAIVE_DEADLINE = DEADLINE.replace(tzinfo=None)
NEW_START = DEADLINE + timedelta(days=2)
NAIVE_NEW_START = NEW_START.replace(tzinfo=None)


@pytest.fixture
def todo_service(test_session, test_user):
    return TodoService(test_session, test_user)


@pytest.fixture
def schedule_service(test_session, test_user):
    return ScheduleService(test_session, test_user)


def _todo_with_projection(todo_service, test_session, tag_group_id):
    todo = todo_service.create_todo(TodoCreate(
        title="역전파 대상 할일",
        tag_group_id=tag_group_id,
        deadline=DEADLINE,
    ))
    test_session.flush()
    test_session.refresh(todo)
    [projection] = schedule_crud.get_schedules_by_source_todo_id(
        test_session, todo.id, todo.owner_id
    )
    return todo, projection


class TestScheduleTimeChangedBackpropagation:
    def test_schedule_time_change_backpropagates_to_todo_deadline(
            self, todo_service, schedule_service, test_session, sample_tag_group):
        """투영 일정의 시간 이동 → Todo.deadline 역투영 (#44)"""
        todo, projection = _todo_with_projection(
            todo_service, test_session, sample_tag_group.id)

        schedule_service.update_schedule(
            projection.id,
            ScheduleUpdate(
                start_time=NEW_START,
                end_time=NEW_START + timedelta(hours=1),
            ),
        )

        test_session.refresh(todo)
        assert todo.deadline == NAIVE_NEW_START

    def test_time_change_on_unlinked_schedule_touches_no_todo(
            self, todo_service, schedule_service, test_session, sample_tag_group):
        """source_todo_id 없는 일반 일정 변경은 어떤 Todo도 건드리지 않음"""
        todo, _ = _todo_with_projection(
            todo_service, test_session, sample_tag_group.id)
        regular = schedule_service.create_schedule(ScheduleCreate(
            title="일반 일정",
            start_time=DEADLINE,
            end_time=DEADLINE + timedelta(hours=1),
        ))

        schedule_service.update_schedule(
            regular.id,
            ScheduleUpdate(
                start_time=NEW_START,
                end_time=NEW_START + timedelta(hours=1),
            ),
        )

        test_session.refresh(todo)
        assert todo.deadline == NAIVE_DEADLINE  # 원래 마감 유지

    def test_recurring_source_linked_schedule_does_not_backpropagate(
            self, todo_service, schedule_service, test_session, sample_tag_group):
        """반복 일정이 된 투영은 역투영 제외 — 시점 마감의 투영이 아님 (결정 고정)"""
        todo, projection = _todo_with_projection(
            todo_service, test_session, sample_tag_group.id)

        # 투영을 반복 일정으로 전환
        schedule_service.update_schedule(
            projection.id,
            ScheduleUpdate(recurrence_rule="FREQ=WEEKLY;BYDAY=MO"),
        )
        # 반복 일정의 시간 이동
        schedule_service.update_schedule(
            projection.id,
            ScheduleUpdate(
                start_time=NEW_START,
                end_time=NEW_START + timedelta(hours=1),
            ),
        )

        test_session.refresh(todo)
        assert todo.deadline == NAIVE_DEADLINE  # 역투영 안 됨

    def test_origin_guard_blocks_todo_originated_events(
            self, todo_service, test_session, sample_tag_group, test_user):
        """origin=TODO인 ScheduleTimeChanged는 역투영되지 않음 (가드 직접 검증)

        정방향 핸들러는 Schedule을 직접 수정하고 이벤트를 발행하지 않으므로,
        이 가드는 통상 흐름에서 발화하지 않는다 — 이벤트를 수동 발행해
        가드 단독으로 검증한다.
        """
        from app.domain.schedule.events import ScheduleTimeChanged
        from app.shared.events import EventOrigin
        from app.shared.uow import collect_event, flush_and_dispatch_events

        todo, projection = _todo_with_projection(
            todo_service, test_session, sample_tag_group.id)

        # 핸들러를 거치지 않고 시간만 직접 이동 (역투영 전제 조건 구성)
        projection.start_time = NAIVE_NEW_START
        projection.end_time = NAIVE_NEW_START + timedelta(hours=1)
        test_session.flush()

        # origin=TODO → 가드에 걸려 deadline 미역투영
        collect_event(test_session, ScheduleTimeChanged(
            owner_id=test_user.sub,
            origin=EventOrigin.TODO,
            schedule_id=projection.id,
        ))
        flush_and_dispatch_events(test_session)
        test_session.refresh(todo)
        assert todo.deadline == NAIVE_DEADLINE

        # 동일 상황에서 origin=SCHEDULE이면 역투영됨 → 가드가 유일한 차단자
        collect_event(test_session, ScheduleTimeChanged(
            owner_id=test_user.sub,
            origin=EventOrigin.SCHEDULE,
            schedule_id=projection.id,
        ))
        flush_and_dispatch_events(test_session)
        test_session.refresh(todo)
        assert todo.deadline == NAIVE_NEW_START

    def test_no_pingpong_on_todo_deadline_update(
            self, todo_service, test_session, sample_tag_group):
        """Todo→Schedule 정방향이 역전파를 재촉발하지 않음 (depth 폭주 없이 완료)"""
        from app.domain.todo.schema.dto import TodoUpdate

        todo, _ = _todo_with_projection(
            todo_service, test_session, sample_tag_group.id)

        updated = todo_service.update_todo(todo.id, TodoUpdate(deadline=NEW_START))

        [projection] = schedule_crud.get_schedules_by_source_todo_id(
            test_session, todo.id, todo.owner_id)
        assert updated.deadline == NAIVE_NEW_START
        assert projection.start_time == NAIVE_NEW_START


class TestScheduleDeletedBackpropagation:
    def test_deleting_projected_schedule_keeps_todo_and_deadline(
            self, todo_service, schedule_service, test_session, sample_tag_group):
        """투영 삭제 = 캘린더 표시 제거일 뿐 — 할일·마감 유지, status만 UNSCHEDULED"""
        todo, projection = _todo_with_projection(
            todo_service, test_session, sample_tag_group.id)
        assert todo.status == TodoStatus.SCHEDULED

        schedule_service.delete_schedule(projection.id)

        test_session.refresh(todo)
        assert todo.deadline == NAIVE_DEADLINE  # 마감 유지 (#55 정책)
        assert todo.status == TodoStatus.UNSCHEDULED  # 투영 부재 반영

    def test_deleting_projection_of_done_todo_keeps_terminal_status(
            self, todo_service, schedule_service, test_session, sample_tag_group):
        """터미널 상태(DONE)는 투영 삭제로도 덮이지 않음"""
        from app.domain.todo.schema.dto import TodoUpdate

        todo, projection = _todo_with_projection(
            todo_service, test_session, sample_tag_group.id)
        todo_service.update_todo(todo.id, TodoUpdate(status=TodoStatus.DONE))

        schedule_service.delete_schedule(projection.id)

        test_session.refresh(todo)
        assert todo.status == TodoStatus.DONE


class TestScheduleCreatedWithTodoOption:
    def test_create_schedule_with_todo_option_creates_single_linked_schedule(
            self, schedule_service, test_session, sample_tag_group, test_user):
        """A→B→A 차단: 생성된 Todo의 deadline이 두 번째 일정을 만들지 않음"""
        schedule = schedule_service.create_schedule(ScheduleCreate(
            title="옵션으로 할일 생성",
            description="설명",
            start_time=DEADLINE,
            end_time=DEADLINE + timedelta(hours=1),
            create_todo_options=CreateTodoOptions(tag_group_id=sample_tag_group.id),
        ))
        test_session.refresh(schedule)

        assert schedule.source_todo_id is not None

        # 연결 Todo 검증
        from app.crud import todo as todo_crud
        todo = todo_crud.get_todo(test_session, schedule.source_todo_id, test_user.sub)
        assert todo is not None
        assert todo.title == "옵션으로 할일 생성"
        assert todo.deadline == NAIVE_DEADLINE
        assert todo.status == TodoStatus.SCHEDULED

        # 전체 일정은 정확히 1개 (재발화로 인한 중복 생성 없음)
        all_schedules = schedule_crud.get_schedules(test_session, test_user.sub)
        assert len(all_schedules) == 1
        # 연결 투영도 정확히 1개
        linked = schedule_crud.get_schedules_by_source_todo_id(
            test_session, todo.id, test_user.sub)
        assert len(linked) == 1
