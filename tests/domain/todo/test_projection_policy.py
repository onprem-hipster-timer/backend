"""
투영(projection) 정책 테스트 — 필드 소유권 표 (domain-events.ko.md §5.1)

"할일(Todo)이 원본, 일정(Schedule)은 deadline의 캘린더 투영" 계약을
테스트명으로 고정합니다 (#55, #61).

- status 자동 불변조건: SCHEDULED ⇔ 투영 존재 (터미널 상태 예외)
- linked_schedule_policy: 클라이언트 명시 필수, 서버 디폴트 없음 (#61)
- 제목·설명은 Todo 소유 → 투영 항상 반영
- 일정 길이는 Schedule 소유 → deadline 변경 시 보존
- 투영이 사라진 상태의 deadline 변경 → 재생성
"""
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.crud import schedule as schedule_crud
from app.domain.schedule.schema.dto import ScheduleUpdate
from app.domain.schedule.service import ScheduleService
from app.domain.todo.enums import LinkedSchedulePolicy, TodoStatus
from app.domain.todo.schema.dto import TodoCreate, TodoUpdate
from app.domain.todo.service import TodoService

DEADLINE = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)
NAIVE_DEADLINE = DEADLINE.replace(tzinfo=None)
NEW_DEADLINE = DEADLINE + timedelta(days=1)
NAIVE_NEW_DEADLINE = NEW_DEADLINE.replace(tzinfo=None)


@pytest.fixture
def todo_service(test_session, test_user):
    return TodoService(test_session, test_user)


@pytest.fixture
def schedule_service(test_session, test_user):
    return ScheduleService(test_session, test_user)


def _create_with_deadline(todo_service, test_session, tag_group_id, **overrides):
    data = TodoCreate(
        title="마감 있는 할일",
        tag_group_id=tag_group_id,
        deadline=DEADLINE,
        **overrides,
    )
    todo = todo_service.create_todo(data)
    test_session.flush()
    test_session.refresh(todo)
    return todo


def _projections(test_session, todo_id, owner_id):
    return schedule_crud.get_schedules_by_source_todo_id(test_session, todo_id, owner_id)


# ============================================================
# status 자동 불변조건: SCHEDULED ⇔ 투영 존재 (화석 1·5)
# ============================================================

class TestStatusAutomation:
    def test_create_todo_with_deadline_sets_scheduled_status(
            self, todo_service, test_session, sample_tag_group, test_user):
        """생성 경로 무관 일관: deadline 생성 → 투영 존재 → SCHEDULED"""
        todo = _create_with_deadline(todo_service, test_session, sample_tag_group.id)

        assert todo.status == TodoStatus.SCHEDULED

    def test_create_todo_without_deadline_stays_unscheduled(
            self, todo_service, test_session, sample_tag_group):
        todo = todo_service.create_todo(
            TodoCreate(title="마감 없는 할일", tag_group_id=sample_tag_group.id)
        )

        assert todo.status == TodoStatus.UNSCHEDULED

    def test_terminal_status_not_overridden_on_create(
            self, todo_service, test_session, sample_tag_group):
        """명시적 터미널 상태(DONE/CANCELLED)는 자동화가 덮지 않음"""
        todo = _create_with_deadline(
            todo_service, test_session, sample_tag_group.id, status=TodoStatus.DONE
        )

        assert todo.status == TodoStatus.DONE

    def test_deadline_add_sets_scheduled_status(
            self, todo_service, test_session, sample_tag_group):
        todo = todo_service.create_todo(
            TodoCreate(title="나중에 마감 추가", tag_group_id=sample_tag_group.id)
        )
        assert todo.status == TodoStatus.UNSCHEDULED

        updated = todo_service.update_todo(todo.id, TodoUpdate(deadline=DEADLINE))

        assert updated.status == TodoStatus.SCHEDULED

    def test_deadline_clear_resets_scheduled_to_unscheduled(
            self, todo_service, test_session, sample_tag_group, test_user):
        todo = _create_with_deadline(todo_service, test_session, sample_tag_group.id)

        updated = todo_service.update_todo(
            todo.id,
            TodoUpdate(deadline=None, linked_schedule_policy=LinkedSchedulePolicy.DELETE),
        )

        assert updated.deadline is None
        assert updated.status == TodoStatus.UNSCHEDULED
        assert _projections(test_session, todo.id, test_user.sub) == []

    def test_explicit_status_wins_over_automation(
            self, todo_service, test_session, sample_tag_group):
        """같은 요청에 status가 명시되면 사용자 의도가 우선"""
        todo = todo_service.create_todo(
            TodoCreate(title="명시 상태", tag_group_id=sample_tag_group.id)
        )

        updated = todo_service.update_todo(
            todo.id, TodoUpdate(deadline=DEADLINE, status=TodoStatus.DONE)
        )

        assert updated.status == TodoStatus.DONE


# ============================================================
# linked_schedule_policy 검증 (#61 — 디폴트 없음, 명시 필수)
# ============================================================

class TestLinkedSchedulePolicyValidation:
    def test_deadline_clear_requires_policy(self):
        with pytest.raises(ValidationError):
            TodoUpdate(deadline=None)

    def test_deadline_clear_with_policy_is_valid(self):
        data = TodoUpdate(
            deadline=None, linked_schedule_policy=LinkedSchedulePolicy.DELETE
        )
        assert data.linked_schedule_policy == LinkedSchedulePolicy.DELETE

    def test_policy_without_deadline_clear_rejected(self):
        """정책은 deadline 명시적 null과 함께만 허용 (의미 없는 조합 차단)"""
        with pytest.raises(ValidationError):
            TodoUpdate(linked_schedule_policy=LinkedSchedulePolicy.DELETE)

        with pytest.raises(ValidationError):
            TodoUpdate(
                deadline=DEADLINE,
                linked_schedule_policy=LinkedSchedulePolicy.DELETE,
            )


# ============================================================
# 수명주기 정책: delete vs unlink (#61)
# ============================================================

class TestLifecyclePolicy:
    def test_deadline_clear_unlink_preserves_schedule(
            self, todo_service, test_session, sample_tag_group, test_user):
        """unlink: 투영은 일반 일정으로 생존 (메모·데이터 보존)"""
        todo = _create_with_deadline(todo_service, test_session, sample_tag_group.id)
        [projection] = _projections(test_session, todo.id, test_user.sub)

        todo_service.update_todo(
            todo.id,
            TodoUpdate(deadline=None, linked_schedule_policy=LinkedSchedulePolicy.UNLINK),
        )

        survivor = schedule_crud.get_schedule(test_session, projection.id, test_user.sub)
        assert survivor is not None
        assert survivor.source_todo_id is None
        assert survivor.title == "마감 있는 할일"
        assert _projections(test_session, todo.id, test_user.sub) == []

    def test_delete_todo_delete_policy_removes_projection(
            self, todo_service, test_session, sample_tag_group, test_user):
        todo = _create_with_deadline(todo_service, test_session, sample_tag_group.id)
        [projection] = _projections(test_session, todo.id, test_user.sub)

        todo_service.delete_todo(todo.id, LinkedSchedulePolicy.DELETE)

        assert schedule_crud.get_schedule(test_session, projection.id, test_user.sub) is None

    def test_delete_todo_unlink_policy_keeps_schedule(
            self, todo_service, test_session, sample_tag_group, test_user):
        todo = _create_with_deadline(todo_service, test_session, sample_tag_group.id)
        [projection] = _projections(test_session, todo.id, test_user.sub)

        todo_service.delete_todo(todo.id, LinkedSchedulePolicy.UNLINK)

        survivor = schedule_crud.get_schedule(test_session, projection.id, test_user.sub)
        assert survivor is not None
        assert survivor.source_todo_id is None


# ============================================================
# 투영 동기화: 제목·설명(화석 3), 길이 보존(화석 7), 재생성(화석 2), 단일 투영(화석 4)
# ============================================================

class TestProjectionSync:
    def test_updating_title_projects_latest_title(
            self, todo_service, test_session, sample_tag_group, test_user):
        """제목·설명은 Todo 소유 — 투영은 항상 최신 반영"""
        todo = _create_with_deadline(todo_service, test_session, sample_tag_group.id)

        todo_service.update_todo(
            todo.id, TodoUpdate(title="새 제목", description="새 설명")
        )

        [projection] = _projections(test_session, todo.id, test_user.sub)
        assert projection.title == "새 제목"
        assert projection.description == "새 설명"

    def test_deadline_change_preserves_user_duration(
            self, todo_service, schedule_service, test_session, sample_tag_group, test_user):
        """일정 길이는 Schedule 소유 — deadline 변경은 start만 이동"""
        todo = _create_with_deadline(todo_service, test_session, sample_tag_group.id)
        [projection] = _projections(test_session, todo.id, test_user.sub)

        # 사용자가 투영 길이를 3시간으로 조정
        schedule_service.update_schedule(
            projection.id,
            ScheduleUpdate(end_time=projection.start_time + timedelta(hours=3)),
        )

        todo_service.update_todo(todo.id, TodoUpdate(deadline=NEW_DEADLINE))

        [projection] = _projections(test_session, todo.id, test_user.sub)
        assert projection.start_time == NAIVE_NEW_DEADLINE
        assert projection.end_time - projection.start_time == timedelta(hours=3)

    def test_deadline_change_recreates_missing_projection(
            self, todo_service, schedule_service, test_session, sample_tag_group, test_user):
        """투영이 사라진 상태의 deadline 변경 → 조용한 no-op이 아니라 재생성"""
        todo = _create_with_deadline(todo_service, test_session, sample_tag_group.id)
        [projection] = _projections(test_session, todo.id, test_user.sub)
        schedule_service.delete_schedule(projection.id)

        todo_service.update_todo(todo.id, TodoUpdate(deadline=NEW_DEADLINE))

        [recreated] = _projections(test_session, todo.id, test_user.sub)
        assert recreated.start_time == NAIVE_NEW_DEADLINE
        assert recreated.title == todo.title

    def test_single_projection_invariant_after_unlink_and_readd(
            self, todo_service, test_session, sample_tag_group, test_user):
        """unlink 후 deadline 재설정 → 연결 투영은 정확히 1개"""
        todo = _create_with_deadline(todo_service, test_session, sample_tag_group.id)

        todo_service.update_todo(
            todo.id,
            TodoUpdate(deadline=None, linked_schedule_policy=LinkedSchedulePolicy.UNLINK),
        )
        todo_service.update_todo(todo.id, TodoUpdate(deadline=NEW_DEADLINE))

        projections = _projections(test_session, todo.id, test_user.sub)
        assert len(projections) == 1
        assert projections[0].start_time == NAIVE_NEW_DEADLINE
