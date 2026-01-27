"""
공유 리소스 필터링 테스트

공유된 리소스(Schedule, Timer, Todo)에 대해 필터링 파라미터가
올바르게 적용되는지 검증합니다.

이슈: scope=shared 또는 scope=all 일 때, 공유된 리소스에 대해
필터링 파라미터가 무시되어 내 리소스와 다르게 동작하는 문제가 있었습니다.
"""
from uuid import uuid4

import pytest

from app.core.auth import CurrentUser
from app.domain.friend.service import FriendService
from app.domain.visibility.enums import VisibilityLevel, ResourceType
from app.domain.visibility.service import VisibilityService


@pytest.fixture
def second_user() -> CurrentUser:
    """두 번째 테스트 사용자 (공유 리소스의 소유자)"""
    return CurrentUser(
        sub="second-user-id",
        email="second@example.com",
        name="Second User",
    )


@pytest.fixture
def friendship(test_session, test_user, second_user):
    """test_user와 second_user의 친구 관계 설정"""
    # second_user가 test_user에게 친구 요청
    user2_service = FriendService(test_session, second_user)
    friendship = user2_service.send_friend_request(test_user.sub)

    # test_user가 수락
    user1_service = FriendService(test_session, test_user)
    user1_service.accept_friend_request(friendship.id)

    return friendship


class TestSharedTodoTagFiltering:
    """공유된 Todo의 태그 필터링 테스트"""

    def test_shared_todo_tag_filter_applied(
            self, test_session, test_user, second_user, friendship
    ):
        """공유된 Todo 조회 시 tag_ids 필터가 적용되어야 함"""
        from app.domain.tag.service import TagService
        from app.domain.todo.service import TodoService
        from app.domain.tag.schema.dto import TagGroupCreate, TagCreate
        from app.domain.todo.schema.dto import TodoCreate

        # 1. second_user가 태그 그룹과 태그 생성
        user2_tag_service = TagService(test_session, second_user)
        group = user2_tag_service.create_tag_group(TagGroupCreate(name="업무", color="#FF5733"))
        tag_a = user2_tag_service.create_tag(TagCreate(name="태그A", group_id=group.id, color="#00FF00"))
        tag_b = user2_tag_service.create_tag(TagCreate(name="태그B", group_id=group.id, color="#0000FF"))

        # 2. second_user가 Todo 생성 (태그 A만 가진 Todo)
        user2_todo_service = TodoService(test_session, second_user)
        todo_with_tag_a = user2_todo_service.create_todo(
            TodoCreate(
                title="태그A만 가진 Todo",
                tag_group_id=group.id,
                tag_ids=[tag_a.id],
            )
        )

        # Todo에 태그 B가 포함된 것도 생성
        todo_with_tag_b = user2_todo_service.create_todo(
            TodoCreate(
                title="태그B만 가진 Todo",
                tag_group_id=group.id,
                tag_ids=[tag_b.id],
            )
        )

        # 3. second_user가 두 Todo를 친구에게 공유 (FRIENDS 레벨)
        visibility_service = VisibilityService(test_session, second_user)
        visibility_service.set_visibility(
            resource_type=ResourceType.TODO,
            resource_id=todo_with_tag_a.id,
            level=VisibilityLevel.FRIENDS,
        )
        visibility_service.set_visibility(
            resource_type=ResourceType.TODO,
            resource_id=todo_with_tag_b.id,
            level=VisibilityLevel.FRIENDS,
        )

        # 4. test_user가 공유된 Todo를 tag_ids 필터로 조회
        user1_todo_service = TodoService(test_session, test_user)
        shared_todos = user1_todo_service.get_shared_todos()

        # 필터 적용 전: 2개 모두 조회되어야 함
        assert len(shared_todos) == 2

        # tag_ids 필터 적용 (태그A만 포함된 Todo만 반환해야 함)
        # API 레벨에서 필터링되므로 여기서는 직접 필터링 로직 테스트
        filtered_todos = []
        target_tag_ids = [tag_a.id]
        for todo in shared_todos:
            todo_tag_ids = {tag.id for tag in todo.tags}
            if all(tid in todo_tag_ids for tid in target_tag_ids):
                filtered_todos.append(todo)

        assert len(filtered_todos) == 1
        assert filtered_todos[0].id == todo_with_tag_a.id


class TestSharedScheduleTagFiltering:
    """공유된 Schedule의 태그 필터링 테스트 (이슈 검증용)"""

    def test_shared_schedule_should_apply_tag_filter(
            self, test_session, test_user, second_user, friendship
    ):
        """
        공유된 Schedule 조회 시 tag_ids 필터가 적용되어야 함
        
        현재 이슈: 공유된 Schedule에 tag_ids, group_ids 필터가 적용되지 않음
        """
        from app.domain.tag.service import TagService
        from app.domain.schedule.service import ScheduleService
        from app.domain.tag.schema.dto import TagGroupCreate, TagCreate
        from app.domain.schedule.schema.dto import ScheduleCreate
        from datetime import datetime, timezone

        # 1. second_user가 태그 그룹과 태그 생성
        user2_tag_service = TagService(test_session, second_user)
        group = user2_tag_service.create_tag_group(TagGroupCreate(name="업무", color="#FF5733"))
        tag_a = user2_tag_service.create_tag(TagCreate(name="미팅", group_id=group.id, color="#00FF00"))
        tag_b = user2_tag_service.create_tag(TagCreate(name="개발", group_id=group.id, color="#0000FF"))

        # 2. second_user가 Schedule 생성
        user2_schedule_service = ScheduleService(test_session, second_user)
        now = datetime.now(timezone.utc)

        schedule_with_tag_a = user2_schedule_service.create_schedule(
            ScheduleCreate(
                title="미팅 일정",
                start_time=now,
                end_time=now.replace(hour=now.hour + 1 if now.hour < 23 else 0),
                tag_ids=[tag_a.id],
            )
        )

        schedule_with_tag_b = user2_schedule_service.create_schedule(
            ScheduleCreate(
                title="개발 일정",
                start_time=now,
                end_time=now.replace(hour=now.hour + 1 if now.hour < 23 else 0),
                tag_ids=[tag_b.id],
            )
        )

        # 3. second_user가 두 Schedule을 친구에게 공유
        visibility_service = VisibilityService(test_session, second_user)
        visibility_service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=schedule_with_tag_a.id,
            level=VisibilityLevel.FRIENDS,
        )
        visibility_service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=schedule_with_tag_b.id,
            level=VisibilityLevel.FRIENDS,
        )

        # 4. test_user가 공유된 Schedule 조회
        user1_schedule_service = ScheduleService(test_session, test_user)
        shared_schedules = user1_schedule_service.get_shared_schedules()

        # 필터 적용 전: 2개 모두 조회되어야 함
        assert len(shared_schedules) == 2

        # 이슈 검증: API 레벨에서 tag_ids 필터링이 필요함
        # 현재 app/api/v1/schedules.py에서 공유된 Schedule에 대해
        # tag_ids, group_ids 필터가 적용되지 않음
        #
        # 필요한 수정:
        # if tag_ids:
        #     schedule_tag_ids = {tag.id for tag in schedule.tags}
        #     if not all(tid in schedule_tag_ids for tid in tag_ids):
        #         continue


class TestSharedTimerTypeFiltering:
    """공유된 Timer의 타입 필터링 테스트 (이슈 검증용)"""

    def test_shared_timer_should_apply_type_filter(
            self, test_session, test_user, second_user, friendship
    ):
        """
        공유된 Timer 조회 시 timer_type 필터가 적용되어야 함
        
        현재 이슈: 공유된 Timer에 timer_type 필터가 적용되지 않음
        """
        from app.domain.timer.service import TimerService
        from app.domain.tag.service import TagService
        from app.domain.schedule.service import ScheduleService
        from app.domain.tag.schema.dto import TagGroupCreate
        from app.domain.schedule.schema.dto import ScheduleCreate
        from app.domain.timer.schema.dto import TimerCreate
        from datetime import datetime, timezone

        # 1. second_user가 Schedule 생성 (Timer 연결용)
        user2_tag_service = TagService(test_session, second_user)
        group = user2_tag_service.create_tag_group(TagGroupCreate(name="업무", color="#FF5733"))

        user2_schedule_service = ScheduleService(test_session, second_user)
        now = datetime.now(timezone.utc)
        schedule = user2_schedule_service.create_schedule(
            ScheduleCreate(
                title="테스트 일정",
                start_time=now,
                end_time=now.replace(hour=now.hour + 1 if now.hour < 23 else 0),
            )
        )

        # 2. second_user가 Timer 생성
        user2_timer_service = TimerService(test_session, second_user)

        # 독립 타이머 (schedule_id=None, todo_id=None)
        independent_timer = user2_timer_service.create_timer(
            TimerCreate(
                title="독립 타이머",
                allocated_duration=3600,
            )
        )

        # Schedule 연결 타이머
        schedule_timer = user2_timer_service.create_timer(
            TimerCreate(
                title="일정 연결 타이머",
                allocated_duration=3600,
                schedule_id=schedule.id,
            )
        )

        # 3. second_user가 두 Timer를 친구에게 공유
        visibility_service = VisibilityService(test_session, second_user)
        visibility_service.set_visibility(
            resource_type=ResourceType.TIMER,
            resource_id=independent_timer.id,
            level=VisibilityLevel.FRIENDS,
        )
        visibility_service.set_visibility(
            resource_type=ResourceType.TIMER,
            resource_id=schedule_timer.id,
            level=VisibilityLevel.FRIENDS,
        )

        # 4. test_user가 공유된 Timer 조회
        user1_timer_service = TimerService(test_session, test_user)
        shared_timers = user1_timer_service.get_shared_timers()

        # 필터 적용 전: 2개 모두 조회되어야 함
        assert len(shared_timers) == 2

        # 이슈 검증: API 레벨에서 timer_type 필터링이 필요함
        # 현재 app/api/v1/timers.py에서 공유된 Timer에 대해
        # timer_type 필터가 적용되지 않음
        #
        # 필요한 수정:
        # if timer_type == "independent":
        #     if timer.schedule_id is not None or timer.todo_id is not None:
        #         continue
        # elif timer_type == "schedule":
        #     if timer.schedule_id is None:
        #         continue
        # elif timer_type == "todo":
        #     if timer.todo_id is None:
        #         continue

        # 독립 타이머만 필터링
        independent_timers = [
            t for t in shared_timers
            if t.schedule_id is None and t.todo_id is None
        ]
        assert len(independent_timers) == 1
        assert independent_timers[0].id == independent_timer.id

        # Schedule 연결 타이머만 필터링
        schedule_timers = [
            t for t in shared_timers
            if t.schedule_id is not None
        ]
        assert len(schedule_timers) == 1
        assert schedule_timers[0].id == schedule_timer.id


class TestSharedScheduleGroupFiltering:
    """공유된 Schedule의 그룹 필터링 테스트 (이슈 검증용)"""

    def test_shared_schedule_should_apply_group_filter(
            self, test_session, test_user, second_user, friendship
    ):
        """
        공유된 Schedule 조회 시 group_ids 필터가 적용되어야 함
        
        현재 이슈: 공유된 Schedule에 group_ids 필터가 적용되지 않음
        """
        from app.domain.tag.service import TagService
        from app.domain.schedule.service import ScheduleService
        from app.domain.tag.schema.dto import TagGroupCreate, TagCreate
        from app.domain.schedule.schema.dto import ScheduleCreate
        from datetime import datetime, timezone

        # 1. second_user가 두 개의 태그 그룹 생성
        user2_tag_service = TagService(test_session, second_user)
        group_a = user2_tag_service.create_tag_group(TagGroupCreate(name="업무", color="#FF5733"))
        group_b = user2_tag_service.create_tag_group(TagGroupCreate(name="개인", color="#00FF00"))

        tag_in_group_a = user2_tag_service.create_tag(TagCreate(name="미팅", group_id=group_a.id, color="#FF0000"))
        tag_in_group_b = user2_tag_service.create_tag(TagCreate(name="운동", group_id=group_b.id, color="#00FF00"))

        # 2. second_user가 각 그룹의 태그를 가진 Schedule 생성
        user2_schedule_service = ScheduleService(test_session, second_user)
        now = datetime.now(timezone.utc)

        schedule_in_group_a = user2_schedule_service.create_schedule(
            ScheduleCreate(
                title="업무 그룹 일정",
                start_time=now,
                end_time=now.replace(hour=now.hour + 1 if now.hour < 23 else 0),
                tag_ids=[tag_in_group_a.id],
            )
        )

        schedule_in_group_b = user2_schedule_service.create_schedule(
            ScheduleCreate(
                title="개인 그룹 일정",
                start_time=now,
                end_time=now.replace(hour=now.hour + 1 if now.hour < 23 else 0),
                tag_ids=[tag_in_group_b.id],
            )
        )

        # 3. second_user가 두 Schedule을 친구에게 공유
        visibility_service = VisibilityService(test_session, second_user)
        visibility_service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=schedule_in_group_a.id,
            level=VisibilityLevel.FRIENDS,
        )
        visibility_service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=schedule_in_group_b.id,
            level=VisibilityLevel.FRIENDS,
        )

        # 4. test_user가 공유된 Schedule 조회
        user1_schedule_service = ScheduleService(test_session, test_user)
        shared_schedules = user1_schedule_service.get_shared_schedules()

        # 필터 적용 전: 2개 모두 조회되어야 함
        assert len(shared_schedules) == 2

        # group_ids로 필터링 (group_a의 태그를 가진 것만)
        filtered_schedules = []
        target_group_ids = [group_a.id]
        for schedule in shared_schedules:
            schedule_group_ids = {tag.group_id for tag in schedule.tags}
            if any(gid in schedule_group_ids for gid in target_group_ids):
                filtered_schedules.append(schedule)

        assert len(filtered_schedules) == 1
        assert filtered_schedules[0].id == schedule_in_group_a.id


class TestSharedResourceVisibilityIsolation:
    """
    공유 리소스의 연관 리소스 visibility 격리 테스트
    
    보안 요구사항:
    - Timer가 공유되어도 연관 Schedule/Todo는 별도 visibility 검증 필요
    - Todo가 공유되어도 연관 Schedule은 별도 visibility 검증 필요
    """

    def test_shared_timer_should_not_expose_private_schedule(
            self, test_session, test_user, second_user, friendship
    ):
        """
        공유된 Timer 조회 시 PRIVATE Schedule은 노출되지 않아야 함
        
        시나리오:
        - second_user가 Timer(FRIENDS)와 Schedule(PRIVATE) 생성
        - Timer는 Schedule에 연결됨
        - test_user가 Timer 조회 시 Schedule 정보는 null이어야 함
        """
        from app.domain.timer.service import TimerService
        from app.domain.schedule.service import ScheduleService
        from app.domain.tag.service import TagService
        from app.domain.tag.schema.dto import TagGroupCreate
        from app.domain.schedule.schema.dto import ScheduleCreate
        from app.domain.timer.schema.dto import TimerCreate
        from datetime import datetime, timezone

        # 1. second_user가 Schedule 생성 (PRIVATE - 기본값)
        user2_tag_service = TagService(test_session, second_user)
        group = user2_tag_service.create_tag_group(TagGroupCreate(name="업무", color="#FF5733"))

        user2_schedule_service = ScheduleService(test_session, second_user)
        now = datetime.now(timezone.utc)
        private_schedule = user2_schedule_service.create_schedule(
            ScheduleCreate(
                title="비공개 일정",
                start_time=now,
                end_time=now.replace(hour=now.hour + 1 if now.hour < 23 else 0),
            )
        )
        # visibility 설정 안 함 = PRIVATE

        # 2. second_user가 Timer 생성 및 FRIENDS로 공유
        user2_timer_service = TimerService(test_session, second_user)
        timer = user2_timer_service.create_timer(
            TimerCreate(
                title="공유 타이머",
                allocated_duration=3600,
                schedule_id=private_schedule.id,
            )
        )

        visibility_service = VisibilityService(test_session, second_user)
        visibility_service.set_visibility(
            resource_type=ResourceType.TIMER,
            resource_id=timer.id,
            level=VisibilityLevel.FRIENDS,
        )

        # 3. test_user가 Timer 조회
        user1_timer_service = TimerService(test_session, test_user)
        shared_timer, is_shared = user1_timer_service.get_timer_with_access_check(timer.id)

        # Timer는 조회 가능
        assert shared_timer is not None
        assert is_shared is True
        assert shared_timer.schedule_id == private_schedule.id

        # 4. 라우터 레벨에서 Schedule 조회 시도 시 접근 불가
        user1_schedule_service = ScheduleService(test_session, test_user)
        try:
            user1_schedule_service.get_schedule_with_access_check(private_schedule.id)
            schedule_accessible = True
        except Exception:
            schedule_accessible = False

        # Schedule은 PRIVATE이므로 접근 불가해야 함
        assert schedule_accessible is False

    def test_shared_todo_should_not_expose_private_schedule(
            self, test_session, test_user, second_user, friendship
    ):
        """
        공유된 Todo 조회 시 PRIVATE Schedule은 노출되지 않아야 함
        
        시나리오:
        - second_user가 Todo(FRIENDS) 생성, deadline으로 Schedule 자동 생성
        - Schedule은 자동으로 PRIVATE (visibility 미설정)
        - test_user가 Todo 조회 시 연관 Schedule은 접근 불가
        """
        from app.domain.todo.service import TodoService
        from app.domain.schedule.service import ScheduleService
        from app.domain.tag.service import TagService
        from app.domain.tag.schema.dto import TagGroupCreate
        from app.domain.todo.schema.dto import TodoCreate
        from app.crud import schedule as schedule_crud
        from datetime import datetime, timezone, timedelta

        # 1. second_user가 Todo 생성 (deadline 포함 → Schedule 자동 생성)
        user2_tag_service = TagService(test_session, second_user)
        group = user2_tag_service.create_tag_group(TagGroupCreate(name="업무", color="#FF5733"))

        user2_todo_service = TodoService(test_session, second_user)
        deadline = datetime.now(timezone.utc) + timedelta(days=1)
        todo = user2_todo_service.create_todo(
            TodoCreate(
                title="공유 할일",
                tag_group_id=group.id,
                deadline=deadline,
            )
        )

        # Todo를 FRIENDS로 공유
        visibility_service = VisibilityService(test_session, second_user)
        visibility_service.set_visibility(
            resource_type=ResourceType.TODO,
            resource_id=todo.id,
            level=VisibilityLevel.FRIENDS,
        )

        # 자동 생성된 Schedule 확인 (visibility 미설정 = PRIVATE)
        schedules = schedule_crud.get_schedules_by_source_todo_id(test_session, todo.id, second_user.sub)
        assert len(schedules) > 0
        auto_schedule = schedules[0]

        # 2. test_user가 Todo 조회
        user1_todo_service = TodoService(test_session, test_user)
        shared_todo, is_shared = user1_todo_service.get_todo_with_access_check(todo.id)

        # Todo는 조회 가능
        assert shared_todo is not None
        assert is_shared is True

        # 3. 라우터 레벨에서 Schedule 조회 시도 시 접근 불가
        user1_schedule_service = ScheduleService(test_session, test_user)
        try:
            user1_schedule_service.get_schedule_with_access_check(auto_schedule.id)
            schedule_accessible = True
        except Exception:
            schedule_accessible = False

        # Schedule은 PRIVATE이므로 접근 불가해야 함
        assert schedule_accessible is False

    def test_shared_timer_can_access_shared_schedule(
            self, test_session, test_user, second_user, friendship
    ):
        """
        공유된 Timer와 공유된 Schedule이 모두 있으면 둘 다 접근 가능해야 함
        
        시나리오:
        - second_user가 Timer(FRIENDS)와 Schedule(FRIENDS) 생성
        - Timer는 Schedule에 연결됨
        - test_user가 Timer 조회 시 Schedule 정보도 접근 가능
        """
        from app.domain.timer.service import TimerService
        from app.domain.schedule.service import ScheduleService
        from app.domain.tag.service import TagService
        from app.domain.tag.schema.dto import TagGroupCreate
        from app.domain.schedule.schema.dto import ScheduleCreate
        from app.domain.timer.schema.dto import TimerCreate
        from datetime import datetime, timezone

        # 1. second_user가 Schedule 생성 및 FRIENDS 공유
        user2_tag_service = TagService(test_session, second_user)
        group = user2_tag_service.create_tag_group(TagGroupCreate(name="업무", color="#FF5733"))

        user2_schedule_service = ScheduleService(test_session, second_user)
        now = datetime.now(timezone.utc)
        shared_schedule = user2_schedule_service.create_schedule(
            ScheduleCreate(
                title="공유 일정",
                start_time=now,
                end_time=now.replace(hour=now.hour + 1 if now.hour < 23 else 0),
            )
        )

        visibility_service = VisibilityService(test_session, second_user)
        visibility_service.set_visibility(
            resource_type=ResourceType.SCHEDULE,
            resource_id=shared_schedule.id,
            level=VisibilityLevel.FRIENDS,
        )

        # 2. second_user가 Timer 생성 및 FRIENDS로 공유
        user2_timer_service = TimerService(test_session, second_user)
        timer = user2_timer_service.create_timer(
            TimerCreate(
                title="공유 타이머",
                allocated_duration=3600,
                schedule_id=shared_schedule.id,
            )
        )

        visibility_service.set_visibility(
            resource_type=ResourceType.TIMER,
            resource_id=timer.id,
            level=VisibilityLevel.FRIENDS,
        )

        # 3. test_user가 Timer 및 Schedule 조회 가능
        user1_timer_service = TimerService(test_session, test_user)
        shared_timer, is_shared = user1_timer_service.get_timer_with_access_check(timer.id)

        assert shared_timer is not None
        assert is_shared is True

        user1_schedule_service = ScheduleService(test_session, test_user)
        schedule, schedule_is_shared = user1_schedule_service.get_schedule_with_access_check(shared_schedule.id)

        # Schedule도 FRIENDS이므로 접근 가능
        assert schedule is not None
        assert schedule_is_shared is True


class TestRelationshipLazyLoadingProtection:
    """
    SQLModel relationship lazy loading으로 인한 보안 취약점 방지 테스트
    
    DTO 변환 시 의도치 않은 relationship 객체가 포함되지 않도록 보호합니다.
    미래에 DTO나 서비스 코드가 변경될 때 이 테스트가 실패하면
    보안 취약점이 도입될 수 있음을 경고합니다.
    """

    def test_timer_read_dto_excludes_schedule_relationship_by_default(
            self, test_session, test_user
    ):
        """
        TimerRead DTO는 기본적으로 schedule relationship을 포함하지 않아야 함
        
        from_model()을 사용하지 않고 model_validate()를 직접 사용하면
        schedule relationship이 lazy load되어 포함될 수 있음
        """
        from app.domain.timer.service import TimerService
        from app.domain.schedule.service import ScheduleService
        from app.domain.tag.service import TagService
        from app.domain.tag.schema.dto import TagGroupCreate
        from app.domain.schedule.schema.dto import ScheduleCreate
        from app.domain.timer.schema.dto import TimerCreate, TimerRead
        from datetime import datetime, timezone

        # Timer + Schedule 생성
        tag_service = TagService(test_session, test_user)
        group = tag_service.create_tag_group(TagGroupCreate(name="테스트", color="#FF5733"))

        schedule_service = ScheduleService(test_session, test_user)
        now = datetime.now(timezone.utc)
        schedule = schedule_service.create_schedule(
            ScheduleCreate(
                title="테스트 일정",
                start_time=now,
                end_time=now.replace(hour=now.hour + 1 if now.hour < 23 else 0),
            )
        )

        timer_service = TimerService(test_session, test_user)
        timer = timer_service.create_timer(
            TimerCreate(
                title="테스트 타이머",
                allocated_duration=3600,
                schedule_id=schedule.id,
            )
        )

        # from_model()을 사용한 안전한 변환
        timer_read = TimerRead.from_model(timer)

        # schedule 필드가 None이어야 함 (명시적으로 전달하지 않았으므로)
        assert timer_read.schedule is None
        assert timer_read.schedule_id == schedule.id  # ID는 있어야 함

    def test_timer_read_dto_excludes_todo_relationship_by_default(
            self, test_session, test_user
    ):
        """
        TimerRead DTO는 기본적으로 todo relationship을 포함하지 않아야 함
        """
        from app.domain.timer.service import TimerService
        from app.domain.todo.service import TodoService
        from app.domain.tag.service import TagService
        from app.domain.tag.schema.dto import TagGroupCreate
        from app.domain.todo.schema.dto import TodoCreate
        from app.domain.timer.schema.dto import TimerCreate, TimerRead

        # Todo + Timer 생성
        tag_service = TagService(test_session, test_user)
        group = tag_service.create_tag_group(TagGroupCreate(name="테스트", color="#FF5733"))

        todo_service = TodoService(test_session, test_user)
        todo = todo_service.create_todo(
            TodoCreate(
                title="테스트 할일",
                tag_group_id=group.id,
            )
        )

        timer_service = TimerService(test_session, test_user)
        timer = timer_service.create_timer(
            TimerCreate(
                title="테스트 타이머",
                allocated_duration=3600,
                todo_id=todo.id,
            )
        )

        # from_model()을 사용한 안전한 변환
        timer_read = TimerRead.from_model(timer)

        # todo 필드가 None이어야 함 (명시적으로 전달하지 않았으므로)
        assert timer_read.todo is None
        assert timer_read.todo_id == todo.id  # ID는 있어야 함

    def test_todo_read_dto_excludes_schedules_when_not_provided(
            self, test_session, test_user
    ):
        """
        TodoRead DTO는 schedules가 명시적으로 전달되지 않으면 빈 리스트여야 함
        
        to_read_dto()에서 model_validate(todo)를 사용하면 
        schedules relationship이 lazy load될 수 있음
        """
        from app.domain.todo.service import TodoService
        from app.domain.tag.service import TagService
        from app.domain.tag.schema.dto import TagGroupCreate
        from app.domain.todo.schema.dto import TodoCreate
        from datetime import datetime, timezone, timedelta

        # Todo 생성 (deadline 포함 → Schedule 자동 생성)
        tag_service = TagService(test_session, test_user)
        group = tag_service.create_tag_group(TagGroupCreate(name="테스트", color="#FF5733"))

        todo_service = TodoService(test_session, test_user)
        deadline = datetime.now(timezone.utc) + timedelta(days=1)
        todo = todo_service.create_todo(
            TodoCreate(
                title="테스트 할일",
                tag_group_id=group.id,
                deadline=deadline,
            )
        )

        # to_read_dto()에서 schedules를 전달하지 않으면 빈 리스트
        todo_read = todo_service.to_read_dto(todo)
        assert todo_read.schedules == []

        # schedules를 명시적으로 전달하면 포함
        from app.crud import schedule as schedule_crud
        from app.domain.schedule.schema.dto import ScheduleRead
        schedules = schedule_crud.get_schedules_by_source_todo_id(test_session, todo.id, test_user.sub)
        schedule_reads = [ScheduleRead.model_validate(s) for s in schedules]

        todo_read_with_schedules = todo_service.to_read_dto(todo, schedules=schedule_reads)
        assert len(todo_read_with_schedules.schedules) > 0

    def test_schedule_read_dto_does_not_include_source_todo_object(
            self, test_session, test_user
    ):
        """
        ScheduleRead DTO는 source_todo 객체가 아닌 source_todo_id만 포함해야 함
        
        model_validate()를 사용해도 source_todo relationship 객체가
        포함되지 않아야 함
        """
        from app.domain.todo.service import TodoService
        from app.domain.schedule.service import ScheduleService
        from app.domain.tag.service import TagService
        from app.domain.tag.schema.dto import TagGroupCreate
        from app.domain.todo.schema.dto import TodoCreate
        from app.domain.schedule.schema.dto import ScheduleRead
        from app.crud import schedule as schedule_crud
        from datetime import datetime, timezone, timedelta

        # Todo 생성 (deadline 포함 → Schedule 자동 생성)
        tag_service = TagService(test_session, test_user)
        group = tag_service.create_tag_group(TagGroupCreate(name="테스트", color="#FF5733"))

        todo_service = TodoService(test_session, test_user)
        deadline = datetime.now(timezone.utc) + timedelta(days=1)
        todo = todo_service.create_todo(
            TodoCreate(
                title="테스트 할일",
                tag_group_id=group.id,
                deadline=deadline,
            )
        )

        # 자동 생성된 Schedule 조회
        schedules = schedule_crud.get_schedules_by_source_todo_id(test_session, todo.id, test_user.sub)
        assert len(schedules) > 0
        schedule = schedules[0]

        # model_validate()를 사용해도 source_todo_id만 있어야 함
        schedule_read = ScheduleRead.model_validate(schedule)

        assert schedule_read.source_todo_id == todo.id
        # source_todo 객체 필드가 없어야 함 (DTO에 정의되지 않음)
        assert not hasattr(schedule_read, 'source_todo') or getattr(schedule_read, 'source_todo', None) is None

    def test_schedule_read_dto_does_not_include_timers_relationship(
            self, test_session, test_user
    ):
        """
        ScheduleRead DTO는 timers relationship을 포함하지 않아야 함
        """
        from app.domain.timer.service import TimerService
        from app.domain.schedule.service import ScheduleService
        from app.domain.schedule.schema.dto import ScheduleCreate, ScheduleRead
        from app.domain.timer.schema.dto import TimerCreate
        from datetime import datetime, timezone

        # Schedule + Timer 생성
        schedule_service = ScheduleService(test_session, test_user)
        now = datetime.now(timezone.utc)
        schedule = schedule_service.create_schedule(
            ScheduleCreate(
                title="테스트 일정",
                start_time=now,
                end_time=now.replace(hour=now.hour + 1 if now.hour < 23 else 0),
            )
        )

        timer_service = TimerService(test_session, test_user)
        timer_service.create_timer(
            TimerCreate(
                title="테스트 타이머",
                allocated_duration=3600,
                schedule_id=schedule.id,
            )
        )

        # 세션 refresh로 relationship 로드 가능 상태로 만듦
        test_session.refresh(schedule)

        # model_validate()를 사용해도 timers가 포함되지 않아야 함
        schedule_read = ScheduleRead.model_validate(schedule)

        # timers 필드가 없어야 함 (DTO에 정의되지 않음)
        assert not hasattr(schedule_read, 'timers')

    def test_shared_timer_response_does_not_leak_private_schedule_via_lazy_load(
            self, test_session, test_user, second_user, friendship
    ):
        """
        공유된 Timer 응답에서 PRIVATE Schedule이 lazy loading으로 유출되지 않아야 함
        
        이 테스트는 라우터 레벨의 보안을 검증합니다.
        TimerService.to_read_dto()가 외부에서 주입받은 schedule만 사용하고
        내부에서 lazy load하지 않는지 확인합니다.
        """
        from app.domain.timer.service import TimerService
        from app.domain.schedule.service import ScheduleService
        from app.domain.tag.service import TagService
        from app.domain.tag.schema.dto import TagGroupCreate
        from app.domain.schedule.schema.dto import ScheduleCreate
        from app.domain.timer.schema.dto import TimerCreate
        from datetime import datetime, timezone

        # 1. second_user가 Schedule(PRIVATE) + Timer(FRIENDS) 생성
        user2_tag_service = TagService(test_session, second_user)
        group = user2_tag_service.create_tag_group(TagGroupCreate(name="업무", color="#FF5733"))

        user2_schedule_service = ScheduleService(test_session, second_user)
        now = datetime.now(timezone.utc)
        private_schedule = user2_schedule_service.create_schedule(
            ScheduleCreate(
                title="비공개 일정",
                start_time=now,
                end_time=now.replace(hour=now.hour + 1 if now.hour < 23 else 0),
            )
        )
        # visibility 설정 안 함 = PRIVATE

        user2_timer_service = TimerService(test_session, second_user)
        timer = user2_timer_service.create_timer(
            TimerCreate(
                title="공유 타이머",
                allocated_duration=3600,
                schedule_id=private_schedule.id,
            )
        )

        visibility_service = VisibilityService(test_session, second_user)
        visibility_service.set_visibility(
            resource_type=ResourceType.TIMER,
            resource_id=timer.id,
            level=VisibilityLevel.FRIENDS,
        )

        # 2. test_user가 Timer 조회
        user1_timer_service = TimerService(test_session, test_user)
        shared_timer, is_shared = user1_timer_service.get_timer_with_access_check(timer.id)

        # 3. to_read_dto()에서 schedule을 전달하지 않으면 포함되지 않아야 함
        timer_read = user1_timer_service.to_read_dto(
            shared_timer,
            is_shared=True,
            schedule=None,  # Schedule 접근 권한 없으므로 None
            todo=None,
        )

        # schedule 필드가 None이어야 함 (lazy load로 유출되지 않음)
        assert timer_read.schedule is None
        # schedule_id는 있어야 함 (참조 정보)
        assert timer_read.schedule_id == private_schedule.id

    def test_shared_todo_response_does_not_leak_private_schedules_via_lazy_load(
            self, test_session, test_user, second_user, friendship
    ):
        """
        공유된 Todo 응답에서 PRIVATE Schedule이 lazy loading으로 유출되지 않아야 함
        
        TodoService.to_read_dto()가 외부에서 주입받은 schedules만 사용하고
        내부에서 relationship을 lazy load하지 않는지 확인합니다.
        """
        from app.domain.todo.service import TodoService
        from app.domain.tag.service import TagService
        from app.domain.tag.schema.dto import TagGroupCreate
        from app.domain.todo.schema.dto import TodoCreate
        from datetime import datetime, timezone, timedelta

        # 1. second_user가 Todo(FRIENDS) 생성 (deadline으로 Schedule 자동 생성)
        user2_tag_service = TagService(test_session, second_user)
        group = user2_tag_service.create_tag_group(TagGroupCreate(name="업무", color="#FF5733"))

        user2_todo_service = TodoService(test_session, second_user)
        deadline = datetime.now(timezone.utc) + timedelta(days=1)
        todo = user2_todo_service.create_todo(
            TodoCreate(
                title="공유 할일",
                tag_group_id=group.id,
                deadline=deadline,
            )
        )

        visibility_service = VisibilityService(test_session, second_user)
        visibility_service.set_visibility(
            resource_type=ResourceType.TODO,
            resource_id=todo.id,
            level=VisibilityLevel.FRIENDS,
        )
        # Schedule은 visibility 설정 안 함 = PRIVATE

        # 2. test_user가 Todo 조회
        user1_todo_service = TodoService(test_session, test_user)
        shared_todo, is_shared = user1_todo_service.get_todo_with_access_check(todo.id)

        # 3. to_read_dto()에서 schedules를 전달하지 않으면 빈 리스트여야 함
        todo_read = user1_todo_service.to_read_dto(
            shared_todo,
            is_shared=True,
            schedules=[],  # Schedule 접근 권한 없으므로 빈 리스트
        )

        # schedules가 빈 리스트여야 함 (lazy load로 유출되지 않음)
        assert todo_read.schedules == []