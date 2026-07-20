"""
Schedule Service

FastAPI Best Practices:
- Service는 비즈니스 로직을 담당
- CRUD 함수를 직접 사용 (Repository 패턴 제거)
- Domain Exception을 발생시켜 비즈니스 규칙 위반 표현
- 모든 datetime을 UTC naive로 변환하여 저장 (모든 DB 구조에서 일관성 보장)

내부 서비스:
- RecurringScheduleService: 반복 일정 인스턴스 관리
- ScheduleQueryService: 날짜 범위 조회 및 태그 필터링
"""
from datetime import datetime
from typing import List, Optional, TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from app.domain.todo.model import Todo

from sqlmodel import Session

from app.core.auth import CurrentUser
from app.crud import schedule as crud
from app.crud import visibility as visibility_crud
from app.domain.schedule.exceptions import (
    ScheduleNotFoundError,
    InvalidRecurrenceRuleError,
    InvalidRecurrenceEndError,
    ScheduleAlreadyLinkedToTodoError,
    SourceTodoPolicyRequiredError,
)
from app.domain.schedule.enums import SourceTodoPolicy
from app.domain.schedule.events import (
    ScheduleCreatedWithTodoOption,
    ScheduleDeleted,
    ScheduleTimeChanged,
    ScheduleUnlinkedFromTodo,
)
from app.domain.schedule.model import Schedule
from app.domain.schedule.query_service import ScheduleQueryService
from app.domain.schedule.recurring_service import RecurringScheduleService
from app.domain.schedule.schema.dto import ScheduleCreate, ScheduleUpdate
from app.domain.visibility.enums import VisibilityLevel, ResourceType
from app.domain.visibility.service import VisibilityService
from app.shared.events import EventOrigin
from app.shared.uow import collect_event, flush_and_dispatch_events
from app.utils.recurrence import RecurrenceCalculator


class ScheduleService:
    """
    Schedule Service - 비즈니스 로직

    FastAPI Best Practices:
    - Repository 패턴 제거, CRUD 함수 직접 사용
    - Session을 받아서 CRUD 함수 호출
    - 모든 datetime을 UTC naive로 변환하여 저장 (모든 DB 구조에서 일관성 보장)
    - CurrentUser를 받아서 사용자별 데이터 격리
    """

    def __init__(self, session: Session, current_user: CurrentUser):
        self.session = session
        self.current_user = current_user
        self.owner_id = current_user.sub
        self._recurring = RecurringScheduleService(session, self.owner_id)
        self._query = ScheduleQueryService(session, self.owner_id)

    # ========================================
    # CRUD
    # ========================================

    def create_schedule(self, data: ScheduleCreate) -> Schedule:
        """
        일정 생성

        비즈니스 로직:
        - 모든 datetime을 UTC naive로 변환하여 저장 (DTO에서 보장)
        - 모든 DB 구조에서 일관성 보장
        - 반복 일정 필드도 함께 저장
        - RRULE 검증
        - 태그 설정 (tag_ids가 있는 경우)
        - create_todo_options가 있으면 Todo도 함께 생성

        :param data: 일정 생성 데이터 (datetime은 DTO에서 UTC naive로 변환됨)
        :return: 생성된 일정
        :raises InvalidRecurrenceRuleError: RRULE 형식이 잘못된 경우
        :raises InvalidRecurrenceEndError: 반복 종료일이 시작일 이전인 경우
        """
        # 반복 일정 검증
        if data.recurrence_rule:
            if not RecurrenceCalculator.is_valid_rrule(data.recurrence_rule):
                raise InvalidRecurrenceRuleError()

            if data.recurrence_end and data.recurrence_end < data.start_time:
                raise InvalidRecurrenceEndError()

        schedule = crud.create_schedule(self.session, data, self.owner_id)

        # 태그 설정
        if data.tag_ids:
            from app.domain.tag.service import TagService
            tag_service = TagService(self.session, self.current_user)
            tag_service.set_schedule_tags(schedule.id, data.tag_ids)
            # 태그 설정 후 relationship 갱신
            self.session.refresh(schedule)

        if data.create_todo_options:
            collect_event(self.session, ScheduleCreatedWithTodoOption(
                owner_id=self.owner_id,
                origin=EventOrigin.SCHEDULE,
                schedule_id=schedule.id,
                tag_group_id=data.create_todo_options.tag_group_id,
            ))

        # 응답 조립 전에 dispatch해야 source_todo_id가 응답에 보인다
        flush_and_dispatch_events(self.session)
        if data.create_todo_options:
            self.session.refresh(schedule)

        return schedule

    def get_schedule(self, schedule_id: UUID) -> Schedule:
        """
        일정 조회 (본인 소유만)

        :param schedule_id: 일정 ID
        :return: 일정
        :raises ScheduleNotFoundError: 일정을 찾을 수 없는 경우
        """
        schedule = crud.get_schedule(self.session, schedule_id, self.owner_id)
        if not schedule:
            raise ScheduleNotFoundError()
        return schedule

    def update_schedule(
            self,
            schedule_id: UUID,
            data: ScheduleUpdate,
    ) -> Schedule:
        """
        일정 업데이트 (일반 일정만)

        비즈니스 로직:
        - 모든 datetime을 UTC naive로 변환하여 저장 (DTO에서 보장)
        - 모든 DB 구조에서 일관성 보장
        - 반복 일정 필드 검증 (recurrence_end가 start_time 이후인지 확인)

        :param schedule_id: 일정 ID
        :param data: 업데이트 데이터 (datetime은 DTO에서 UTC naive로 변환됨)
        :return: 업데이트된 일정
        :raises ScheduleNotFoundError: 일정을 찾을 수 없는 경우
        :raises InvalidRecurrenceRuleError: RRULE 형식이 잘못된 경우
        :raises InvalidRecurrenceEndError: 반복 종료일이 시작일 이전인 경우
        """
        schedule = crud.get_schedule(self.session, schedule_id, self.owner_id)
        if not schedule:
            raise ScheduleNotFoundError()

        # 설정된 필드만 가져오기 (MISSING 필드는 자동 제외)
        update_dict = data.model_dump()

        # datetime 필드 추출 (DTO에서 이미 UTC naive로 변환됨)
        start_time_utc = update_dict.get('start_time', schedule.start_time)
        recurrence_end_utc = update_dict.get('recurrence_end', schedule.recurrence_end)

        # 반복 일정 검증 (recurrence_rule 또는 recurrence_end가 업데이트되는 경우)
        recurrence_rule = update_dict.get('recurrence_rule', schedule.recurrence_rule)
        if recurrence_rule:
            if 'recurrence_rule' in update_dict:
                # 새로운 recurrence_rule이 제공된 경우 검증
                if not RecurrenceCalculator.is_valid_rrule(recurrence_rule):
                    raise InvalidRecurrenceRuleError()

            # recurrence_end 검증 (업데이트되거나 기존 값이 있는 경우)
            if recurrence_end_utc is not None:
                if recurrence_end_utc < start_time_utc:
                    raise InvalidRecurrenceEndError()
            elif schedule.recurrence_end and schedule.recurrence_end < start_time_utc:
                # start_time이 업데이트되어 기존 recurrence_end와 충돌하는 경우
                raise InvalidRecurrenceEndError()

        # source-linked 일정의 반복 전환 = 마감 투영이기를 그만두는 것 —
        # source Todo 처리 정책이 필수이며, 전환은 연결 해제를 동반한다
        converting_to_recurring = (
            'recurrence_rule' in update_dict
            and update_dict['recurrence_rule'] is not None
        )
        if converting_to_recurring and schedule.source_todo_id is not None:
            policy_value = update_dict.get('source_todo_policy')
            if policy_value is None:
                raise SourceTodoPolicyRequiredError()
            collect_event(self.session, ScheduleUnlinkedFromTodo(
                owner_id=self.owner_id,
                origin=EventOrigin.SCHEDULE,
                schedule_id=schedule.id,
                source_todo_id=schedule.source_todo_id,
                policy=SourceTodoPolicy(policy_value),
            ))
            schedule.source_todo_id = None

        # 태그 업데이트 (tag_ids가 설정된 경우에만)
        tag_ids_updated = 'tag_ids' in update_dict
        if tag_ids_updated:
            from app.domain.tag.service import TagService
            tag_service = TagService(self.session, self.current_user)
            tag_service.set_schedule_tags(schedule.id, update_dict['tag_ids'] or [])
        updated_schedule = crud.update_schedule(self.session, schedule, data)

        # 태그가 업데이트된 경우 relationship 갱신
        if tag_ids_updated:
            self.session.refresh(updated_schedule)

        # 반복 일정 제외 판정은 핸들러가 수행하므로 여기서는 연결 여부만 본다
        if 'start_time' in update_dict and updated_schedule.source_todo_id is not None:
            collect_event(self.session, ScheduleTimeChanged(
                owner_id=self.owner_id,
                origin=EventOrigin.SCHEDULE,
                schedule_id=updated_schedule.id,
            ))

        flush_and_dispatch_events(self.session)

        return updated_schedule

    def delete_schedule(
            self,
            schedule_id: UUID,
            source_todo_policy: Optional[SourceTodoPolicy] = None,
    ) -> None:
        """
        일정 삭제

        비즈니스 로직:
        - DB 레벨 CASCADE DELETE로 관련 예외 인스턴스 자동 삭제
        - 접근권한 설정도 함께 삭제
        - 모든 DB 구조에서 일관성 보장

        :param schedule_id: 일정 ID
        :raises ScheduleNotFoundError: 일정을 찾을 수 없는 경우
        """
        schedule = crud.get_schedule(self.session, schedule_id, self.owner_id)
        if not schedule:
            raise ScheduleNotFoundError()

        # source-linked 일정이면 source Todo 처리 정책 필수 (연결 없으면 불필요)
        if schedule.source_todo_id is not None and source_todo_policy is None:
            raise SourceTodoPolicyRequiredError()

        # source_todo_id는 row가 사라지면 조회할 수 없으므로 삭제 전에 스냅샷
        collect_event(self.session, ScheduleDeleted(
            owner_id=self.owner_id,
            origin=EventOrigin.SCHEDULE,
            schedule_id=schedule_id,
            source_todo_id=schedule.source_todo_id,
            policy=source_todo_policy,
        ))

        # 접근권한 설정 삭제
        visibility_crud.delete_visibility_by_resource(
            self.session, ResourceType.SCHEDULE, schedule_id
        )

        crud.delete_schedule(self.session, schedule)

        flush_and_dispatch_events(self.session)

    # ========================================
    # 접근 제어
    # ========================================

    def get_schedule_with_access_check(self, schedule_id: UUID) -> tuple[Schedule, bool]:
        """
        일정 조회 (공유 리소스 접근 제어 포함)

        본인 소유이거나 공유 접근 권한이 있는 경우 반환합니다.

        :param schedule_id: 일정 ID
        :return: (일정, is_shared) 튜플
        :raises ScheduleNotFoundError: 일정을 찾을 수 없는 경우
        :raises AccessDeniedError: 접근 권한이 없는 경우
        """

        # 먼저 ID로만 조회 (소유자 무관)
        schedule = crud.get_schedule_by_id(self.session, schedule_id)
        if not schedule:
            raise ScheduleNotFoundError()

        # 본인 소유인 경우
        if schedule.owner_id == self.owner_id:
            return schedule, False

        # 타인 소유인 경우 접근 권한 확인
        visibility_service = VisibilityService(self.session, self.current_user)
        visibility_service.require_access(
            resource_type=ResourceType.SCHEDULE,
            resource_id=schedule_id,
            owner_id=schedule.owner_id,
        )

        return schedule, True

    def try_get_schedule_read(self, schedule_id: UUID) -> Optional["ScheduleRead"]:
        """
        Schedule 권한 검증 후 DTO 반환 (공통 메서드)

        외부(라우터, 다른 서비스)에서 사용하는 공통 메서드입니다.
        권한이 없거나 리소스가 없으면 None을 반환합니다 (예외 발생 안 함).

        [보안 설계] 각 도메인 서비스가 자신의 리소스에 대한 권한 검증을 담당합니다.
        라우터나 다른 서비스에서 이 메서드를 호출하여 안전하게 연관 리소스를 조회합니다.

        :param schedule_id: Schedule ID
        :return: ScheduleRead DTO 또는 None (권한 없거나 리소스 없음)
        """
        from app.domain.visibility.exceptions import AccessDeniedError

        try:
            schedule, is_shared = self.get_schedule_with_access_check(schedule_id)
            return self.to_read_dto(schedule, is_shared=is_shared)
        except (ScheduleNotFoundError, AccessDeniedError):
            return None

    def get_all_schedules(self) -> list[Schedule]:
        """
        모든 일정 조회 (본인 소유만)

        :return: 일정 리스트
        """
        return crud.get_schedules(self.session, self.owner_id)

    def get_shared_schedules(self) -> list[Schedule]:
        """
        공유된 일정 조회 (타인 소유, 접근 권한 있는 것만)

        N+1 문제 방지를 위해 배치 패턴 사용:
        1. visibility 후보 목록 조회
        2. 리소스 배치 조회
        3. 배치 권한 필터링

        :return: 공유된 일정 리스트
        """
        # 1. 후보 목록 조회 (visibility != PRIVATE, owner != me)
        visibilities = visibility_crud.get_shared_visibilities(
            self.session,
            ResourceType.SCHEDULE,
            exclude_owner_id=self.owner_id,
        )

        if not visibilities:
            return []

        # 2. 리소스 ID 추출 및 배치 조회
        resource_ids = [v.resource_id for v in visibilities]
        schedules = crud.get_schedules_by_ids(self.session, resource_ids)

        if not schedules:
            return []

        # 3. 배치 권한 필터링
        visibility_service = VisibilityService(self.session, self.current_user)
        return visibility_service.filter_accessible_resources(
            resource_type=ResourceType.SCHEDULE,
            visibilities=visibilities,
            resources=schedules,
            get_resource_id=lambda s: s.id,
        )

    # ========================================
    # 조회 및 태그 필터링 (→ ScheduleQueryService)
    # ========================================

    def get_all_schedules_with_tag_filter(
            self,
            tag_ids: Optional[List[UUID]] = None,
            group_ids: Optional[List[UUID]] = None,
    ) -> list[Schedule]:
        """모든 일정 조회 (태그 필터링 지원)"""
        return self._query.get_all_schedules_with_tag_filter(tag_ids, group_ids)

    def get_schedules_by_date_range(
            self,
            start_date: datetime,
            end_date: datetime,
            tag_ids: Optional[List[UUID]] = None,
            group_ids: Optional[List[UUID]] = None,
    ) -> list[Schedule]:
        """날짜 범위로 일정 조회 (반복 일정 포함, 태그 필터링 지원)"""
        return self._query.get_schedules_by_date_range(start_date, end_date, tag_ids, group_ids)

    def get_schedule_tags(self, schedule_id: UUID) -> list:
        """일정의 태그 조회"""
        return self._query.get_schedule_tags(schedule_id)

    # ========================================
    # 반복 일정 인스턴스 관리 (→ RecurringScheduleService)
    # ========================================

    def update_recurring_instance(
            self,
            parent_id: UUID,
            instance_start: datetime,
            data: ScheduleUpdate,
    ) -> Schedule:
        """반복 일정의 특정 인스턴스 수정"""
        return self._recurring.update_recurring_instance(parent_id, instance_start, data, self.current_user)

    def delete_recurring_instance(
            self,
            parent_id: UUID,
            instance_start: datetime,
    ) -> None:
        """반복 일정의 특정 인스턴스 삭제"""
        self._recurring.delete_recurring_instance(parent_id, instance_start)
        # 마지막 인스턴스 소진으로 원본이 삭제됐다면 ScheduleDeleted가 수집돼 있음
        flush_and_dispatch_events(self.session)

    # ========================================
    # Todo 연동
    # ========================================

    def create_todo_from_schedule(self, schedule_id: UUID, tag_group_id: UUID) -> "Todo":
        """
        기존 Schedule에서 연관된 Todo 생성

        비즈니스 로직:
        - 이미 source_todo_id가 있는 Schedule인 경우 에러 발생
        - Schedule의 title, description, start_time(->deadline)을 Todo에 복사
        - Schedule의 tags를 Todo에도 복사
        - Todo 생성 후 Schedule의 source_todo_id 업데이트

        :param schedule_id: Schedule ID
        :param tag_group_id: Todo가 속할 그룹 ID (필수)
        :return: 생성된 Todo
        :raises ScheduleNotFoundError: Schedule을 찾을 수 없는 경우
        :raises ScheduleAlreadyLinkedToTodoError: 이미 Todo와 연결된 Schedule인 경우
        """

        schedule = self.get_schedule(schedule_id)

        # 이미 Todo와 연결된 경우 에러
        if schedule.source_todo_id is not None:
            raise ScheduleAlreadyLinkedToTodoError()

        collect_event(self.session, ScheduleCreatedWithTodoOption(
            owner_id=self.owner_id,
            origin=EventOrigin.SCHEDULE,
            schedule_id=schedule.id,
            tag_group_id=tag_group_id,
        ))
        flush_and_dispatch_events(self.session)
        self.session.refresh(schedule)

        from app.crud import todo as todo_crud
        todo = todo_crud.get_todo(self.session, schedule.source_todo_id, self.owner_id)
        return todo

    # ========================================
    # DTO 변환 및 접근권한
    # ========================================

    def get_schedule_visibility(self, schedule_id: UUID) -> Optional[VisibilityLevel]:
        """
        일정의 접근권한 레벨 조회

        :param schedule_id: 일정 ID
        :return: 접근권한 레벨 (설정되지 않은 경우 None = PRIVATE)
        """
        visibility = visibility_crud.get_visibility_by_resource(
            self.session, ResourceType.SCHEDULE, schedule_id
        )
        return visibility.level if visibility else None

    def to_read_dto(
            self,
            schedule: Schedule,
            is_shared: bool = False,
    ) -> "ScheduleRead":
        """
        Schedule을 ScheduleRead DTO로 변환하고 접근권한 정보를 채웁니다.

        :param schedule: Schedule 모델
        :param is_shared: 공유된 리소스인지 여부
        :return: ScheduleRead DTO (접근권한 정보 포함)
        """
        from app.domain.schedule.schema.dto import ScheduleRead

        schedule_read = ScheduleRead.model_validate(schedule)

        # 접근권한 정보 채우기
        schedule_read.owner_id = schedule.owner_id
        schedule_read.is_shared = is_shared

        # 접근권한 레벨 조회
        visibility = visibility_crud.get_visibility_by_resource(
            self.session, ResourceType.SCHEDULE, schedule.id
        )
        if visibility:
            schedule_read.visibility_level = visibility.level

        return schedule_read
