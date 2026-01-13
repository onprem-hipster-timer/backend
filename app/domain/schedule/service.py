"""
Schedule Service

FastAPI Best Practices:
- Service는 비즈니스 로직을 담당
- CRUD 함수를 직접 사용 (Repository 패턴 제거)
- Domain Exception을 발생시켜 비즈니스 규칙 위반 표현
- 모든 datetime을 UTC naive로 변환하여 저장 (모든 DB 구조에서 일관성 보장)
"""
from datetime import datetime
from typing import List, Optional, TYPE_CHECKING
from uuid import UUID, uuid4

if TYPE_CHECKING:
    from app.domain.todo.model import Todo

from sqlmodel import Session, select

from app.core.auth import CurrentUser
from app.crud import schedule as crud
from app.domain.dateutil.service import ensure_utc_naive, is_datetime_within_tolerance
from app.domain.schedule.exceptions import (
    ScheduleNotFoundError,
    InvalidRecurrenceRuleError,
    InvalidRecurrenceEndError,
    RecurringScheduleError,
    ScheduleAlreadyLinkedToTodoError,
)
from app.domain.schedule.model import Schedule
from app.domain.schedule.schema.dto import ScheduleCreate, ScheduleUpdate
from app.models.schedule import ScheduleException
from app.models.tag import Tag, ScheduleTag
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

        # create_todo_options가 있으면 Todo도 함께 생성
        if data.create_todo_options:
            todo = self._create_todo_for_schedule(
                schedule=schedule,
                tag_group_id=data.create_todo_options.tag_group_id,
                tag_ids=data.tag_ids,
            )
            # Schedule에 source_todo_id 설정
            schedule.source_todo_id = todo.id
            self.session.flush()
            self.session.refresh(schedule)

        return schedule

    def get_schedule(self, schedule_id: UUID) -> Schedule:
        """
        일정 조회
        
        :param schedule_id: 일정 ID
        :return: 일정
        :raises ScheduleNotFoundError: 일정을 찾을 수 없는 경우
        """
        schedule = crud.get_schedule(self.session, schedule_id, self.owner_id)
        if not schedule:
            raise ScheduleNotFoundError()
        return schedule

    def get_all_schedules(self) -> list[Schedule]:
        """
        모든 일정 조회
        
        :return: 일정 리스트
        """
        return crud.get_schedules(self.session, self.owner_id)

    def get_all_schedules_with_tag_filter(
            self,
            tag_ids: Optional[List[UUID]] = None,
            group_ids: Optional[List[UUID]] = None,
    ) -> list[Schedule]:
        """
        모든 일정 조회 (태그 필터링 지원)
        
        비즈니스 로직:
        - tag_ids: AND 방식 (모든 지정 태그 포함해야 함)
        - group_ids: 해당 그룹의 태그 중 하나라도 있으면 포함
        - 둘 다 지정 시: 그룹 필터링 후 태그 필터링 적용
        
        :param tag_ids: 필터링할 태그 ID 리스트 (AND 방식)
        :param group_ids: 필터링할 그룹 ID 리스트
        :return: 필터링된 일정 리스트
        """
        all_schedules = crud.get_schedules(self.session, self.owner_id)

        # 태그 필터링 적용
        if tag_ids or group_ids:
            return self._filter_schedules_by_tags(all_schedules, tag_ids, group_ids)

        return all_schedules

    def get_schedules_by_date_range(
            self,
            start_date: datetime,
            end_date: datetime,
            tag_ids: Optional[List[UUID]] = None,
            group_ids: Optional[List[UUID]] = None,
    ) -> list[Schedule]:
        """
        날짜 범위로 일정 조회 (반복 일정 포함, 태그 필터링 지원)
        
        비즈니스 로직:
        - 모든 datetime을 UTC naive로 변환하여 조회
        - 반복 일정은 가상 인스턴스로 확장하여 반환
        - 예외 인스턴스 처리 (삭제/수정된 인스턴스)
        - 태그 필터링: AND 방식 (모든 지정 태그 포함)
        - 그룹 필터링: 해당 그룹의 태그 중 하나라도 있으면 포함
        
        :param start_date: 시작 날짜
        :param end_date: 종료 날짜
        :param tag_ids: 필터링할 태그 ID 리스트 (AND 방식)
        :param group_ids: 필터링할 그룹 ID 리스트
        :return: 해당 날짜 범위와 겹치는 모든 일정 (가상 인스턴스 포함)
        """
        # UTC naive datetime으로 변환하여 조회
        start_date_utc = ensure_utc_naive(start_date)
        end_date_utc = ensure_utc_naive(end_date)

        # 1. 일반 일정 조회 (반복 일정 제외)
        regular_schedules = crud.get_schedules_by_date_range(
            self.session, start_date_utc, end_date_utc, self.owner_id
        )
        # 반복 일정이 아닌 것만 필터링
        regular_schedules = [
            s for s in regular_schedules
            if not s.recurrence_rule
        ]

        # 2. 반복 일정 조회 (원본만)
        recurring_schedules = crud.get_recurring_schedules(
            self.session, start_date_utc, end_date_utc, self.owner_id
        )

        # 3. 예외 인스턴스 조회 및 인덱싱
        exceptions = crud.get_schedule_exceptions(
            self.session, start_date_utc, end_date_utc, self.owner_id
        )

        # 예외를 한 번만 순회하여 dict와 parent별 그룹화 동시 생성
        exception_dict = {}
        exceptions_by_parent = {}
        for exc in exceptions:
            # 정확한 매칭용 딕셔너리
            exception_dict[(exc.parent_id, exc.exception_date)] = exc

            # parent별 그룹화 (허용 오차 검색용)
            if exc.parent_id not in exceptions_by_parent:
                exceptions_by_parent[exc.parent_id] = []
            exceptions_by_parent[exc.parent_id].append(exc)

        # 4. 반복 일정을 가상 인스턴스로 확장
        virtual_instances = []
        for schedule in recurring_schedules:
            if not schedule.recurrence_rule:
                continue

            instances = RecurrenceCalculator.expand_recurrence(
                schedule.start_time,
                schedule.end_time,
                schedule.recurrence_rule,
                schedule.recurrence_end,
                start_date_utc,
                end_date_utc,
            )

            # 예외 처리: 삭제/수정된 인스턴스 처리
            for instance_start, instance_end in instances:

                exception = exception_dict.get((schedule.id, instance_start))

                # 정확히 매칭되지 않으면 시간 허용 오차 검색 (해당 parent_id의 예외만)
                if exception is None and schedule.id in exceptions_by_parent:
                    for exc in exceptions_by_parent[schedule.id]:
                        if is_datetime_within_tolerance(exc.exception_date, instance_start):
                            exception = exc
                            break

                if exception and exception.is_deleted:
                    continue  # 삭제된 인스턴스는 제외

                # 가상 인스턴스 생성
                virtual_schedule = self._create_virtual_instance(
                    schedule, instance_start, instance_end, exception
                )
                virtual_instances.append(virtual_schedule)

        # 5. 일반 일정 + 가상 인스턴스 합치기
        all_schedules = list(regular_schedules) + virtual_instances

        # 6. 태그 필터링 적용
        if tag_ids or group_ids:
            all_schedules = self._filter_schedules_by_tags(
                all_schedules, tag_ids, group_ids
            )

        # 7. 시간순 정렬
        return sorted(all_schedules, key=lambda s: s.start_time)

    def _create_virtual_instance(
            self,
            schedule: Schedule,
            instance_start: datetime,
            instance_end: datetime,
            exception: ScheduleException | None = None,
    ) -> Schedule:
        """
        가상 인스턴스 생성 (예외 처리 포함)
        
        Bug Fix: 각 가상 인스턴스에 고유 ID 생성
        - 부모 일정의 ID를 재사용하면 여러 인스턴스가 같은 ID를 가지게 됨
        - UUID를 사용하여 각 인스턴스에 고유 ID 할당
        
        :param schedule: 원본 일정
        :param instance_start: 인스턴스 시작 시간
        :param instance_end: 인스턴스 종료 시간
        :param exception: 예외 인스턴스 (있는 경우)
        :return: 가상 인스턴스
        """
        # 각 가상 인스턴스에 고유 ID 생성
        virtual_id = uuid4()

        # 예외가 있고 삭제되지 않았으면 예외 데이터 사용
        if exception and not exception.is_deleted:
            return Schedule(
                id=virtual_id,  # 고유 ID 생성
                title=exception.title or schedule.title,
                description=exception.description or schedule.description,
                start_time=exception.start_time or instance_start,
                end_time=exception.end_time or instance_end,
                created_at=schedule.created_at,
                recurrence_rule=None,  # 가상 인스턴스는 반복 규칙 없음
                recurrence_end=None,
                parent_id=schedule.id,
            )

        # 예외가 없으면 원본 데이터 사용
        return Schedule(
            id=virtual_id,  # 고유 ID 생성
            title=schedule.title,
            description=schedule.description,
            start_time=instance_start,
            end_time=instance_end,
            created_at=schedule.created_at,
            recurrence_rule=None,
            recurrence_end=None,
            parent_id=schedule.id,
        )

    def _find_exception(
            self,
            exceptions: list[ScheduleException],
            parent_id: UUID,
            instance_start: datetime,
    ) -> ScheduleException | None:
        """
        특정 인스턴스의 예외 찾기
        
        Bug Fix: 시간까지 비교하여 정확한 인스턴스 매칭
        - 날짜만 비교하면 하루에 여러 인스턴스가 있을 때 구분하지 못함
        - 시간까지 비교하여 정확한 인스턴스와 매칭
        - 약간의 허용 오차를 두어 시간 정밀도 문제 방지 (1분 이내)
        
        :param exceptions: 예외 인스턴스 리스트
        :param parent_id: 원본 일정 ID
        :param instance_start: 인스턴스 시작 시간 (datetime)
        :return: 예외 인스턴스 또는 None
        """
        for exc in exceptions:
            if exc.parent_id == parent_id:
                # 시간까지 비교 (1분 이내 허용 오차)
                if is_datetime_within_tolerance(exc.exception_date, instance_start):
                    return exc
        return None

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

        # 설정된 필드만 가져오기 (exclude_unset=True)
        update_dict = data.model_dump(exclude_unset=True)

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

        # 태그 업데이트 (tag_ids가 설정된 경우에만)
        tag_ids_updated = 'tag_ids' in update_dict
        if tag_ids_updated:
            from app.domain.tag.service import TagService
            tag_service = TagService(self.session, self.current_user)
            tag_service.set_schedule_tags(schedule.id, update_dict['tag_ids'] or [])
            del update_dict['tag_ids']  # CRUD에 전달하지 않음

        # 변환된 dict로 ScheduleUpdate 재생성
        update_data = ScheduleUpdate(**update_dict)

        updated_schedule = crud.update_schedule(self.session, schedule, update_data)

        # 태그가 업데이트된 경우 relationship 갱신
        if tag_ids_updated:
            self.session.refresh(updated_schedule)

        return updated_schedule

    def delete_schedule(self, schedule_id: UUID) -> None:
        """
        일정 삭제
        
        비즈니스 로직:
        - DB 레벨 CASCADE DELETE로 관련 예외 인스턴스 자동 삭제
        - 모든 DB 구조에서 일관성 보장
        
        :param schedule_id: 일정 ID
        :raises ScheduleNotFoundError: 일정을 찾을 수 없는 경우
        """
        schedule = crud.get_schedule(self.session, schedule_id, self.owner_id)
        if not schedule:
            raise ScheduleNotFoundError()

        crud.delete_schedule(self.session, schedule)

    def update_recurring_instance(
            self,
            parent_id: UUID,
            instance_start: datetime,
            data: ScheduleUpdate,
    ) -> Schedule:
        """
        반복 일정의 특정 인스턴스 수정
        
        가상 인스턴스를 수정하면 ScheduleException을 생성하거나 업데이트합니다.
        프론트엔드는 parent_id와 instance_start를 함께 전송합니다.
        
        :param parent_id: 원본 일정 ID
        :param instance_start: 인스턴스 시작 시간
        :param data: 업데이트 데이터
        :return: 수정된 일정 (가상 인스턴스)
        :raises ScheduleNotFoundError: 원본 일정을 찾을 수 없는 경우
        """
        # 원본 일정 조회
        parent_schedule = crud.get_schedule(self.session, parent_id, self.owner_id)
        if not parent_schedule:
            raise ScheduleNotFoundError()

        if not parent_schedule.recurrence_rule:
            raise RecurringScheduleError()

        # instance_start를 UTC naive로 변환
        instance_start_utc = ensure_utc_naive(instance_start)

        # 기존 예외 인스턴스 조회
        existing_exception = crud.get_schedule_exception_by_date(
            self.session, parent_id, instance_start_utc, self.owner_id
        )

        # 업데이트 데이터 준비 (datetime은 DTO에서 UTC naive로 변환됨)
        update_dict = data.model_dump(exclude_unset=True)

        # 태그 ID 추출 (별도 처리)
        tag_ids = update_dict.pop('tag_ids', None)

        # 예외 인스턴스 생성 또는 업데이트
        if existing_exception:
            # 기존 예외 인스턴스 업데이트
            if existing_exception.is_deleted:
                existing_exception.is_deleted = False

            if 'title' in update_dict:
                existing_exception.title = update_dict['title']
            if 'description' in update_dict:
                existing_exception.description = update_dict['description']
            if 'start_time' in update_dict:
                existing_exception.start_time = update_dict['start_time']
            if 'end_time' in update_dict:
                existing_exception.end_time = update_dict['end_time']

            self.session.flush()
            self.session.refresh(existing_exception)

            # 태그 업데이트 (tag_ids가 설정된 경우에만)
            if tag_ids is not None:
                from app.domain.tag.service import TagService
                tag_service = TagService(self.session, self.current_user)
                tag_service.set_schedule_exception_tags(existing_exception.id, tag_ids)

            # 가상 인스턴스 반환
            instance_end = existing_exception.end_time or (
                    instance_start_utc + (parent_schedule.end_time - parent_schedule.start_time)
            )
            return self._create_virtual_instance(
                parent_schedule,
                instance_start_utc,
                instance_end,
                existing_exception
            )
        else:
            # 새 예외 인스턴스 생성
            exception = crud.create_schedule_exception(
                self.session,
                parent_id=parent_id,
                exception_date=instance_start_utc,
                owner_id=self.owner_id,
                is_deleted=False,
                title=update_dict.get('title'),
                description=update_dict.get('description'),
                start_time=update_dict.get('start_time'),
                end_time=update_dict.get('end_time'),
            )

            # 태그 설정 (tag_ids가 설정된 경우에만)
            if tag_ids is not None:
                from app.domain.tag.service import TagService
                tag_service = TagService(self.session, self.current_user)
                tag_service.set_schedule_exception_tags(exception.id, tag_ids)

            # 가상 인스턴스 반환
            instance_end = exception.end_time or (
                    instance_start_utc + (parent_schedule.end_time - parent_schedule.start_time)
            )
            return self._create_virtual_instance(
                parent_schedule,
                instance_start_utc,
                instance_end,
                exception
            )

    def delete_recurring_instance(
            self,
            parent_id: UUID,
            instance_start: datetime,
    ) -> None:
        """
        반복 일정의 특정 인스턴스 삭제
        
        가상 인스턴스를 삭제하면 ScheduleException을 생성하거나 업데이트합니다.
        프론트엔드는 parent_id와 instance_start를 함께 전송합니다.
        
        recurrence_end가 있는 경우, 모든 인스턴스가 삭제되었으면 원본 일정도 자동 삭제됩니다.
        
        :param parent_id: 원본 일정 ID
        :param instance_start: 인스턴스 시작 시간
        :raises ScheduleNotFoundError: 원본 일정을 찾을 수 없는 경우
        """
        # 원본 일정 조회
        parent_schedule = crud.get_schedule(self.session, parent_id, self.owner_id)
        if not parent_schedule:
            raise ScheduleNotFoundError()

        if not parent_schedule.recurrence_rule:
            raise RecurringScheduleError()

        # instance_start를 UTC naive로 변환
        instance_start_utc = ensure_utc_naive(instance_start)

        # 기존 예외 인스턴스 조회
        existing_exception = crud.get_schedule_exception_by_date(
            self.session, parent_id, instance_start_utc, self.owner_id
        )

        if existing_exception:
            # 기존 예외 인스턴스를 삭제로 표시
            existing_exception.is_deleted = True
            self.session.flush()
        else:
            # 새 예외 인스턴스 생성 (삭제 표시)
            crud.create_schedule_exception(
                self.session,
                parent_id=parent_id,
                exception_date=instance_start_utc,
                owner_id=self.owner_id,
                is_deleted=True,
            )

        # recurrence_end가 있는 경우, 모든 인스턴스가 삭제되었는지 확인
        if parent_schedule.recurrence_end:
            if self._are_all_instances_deleted(parent_schedule):
                # 모든 인스턴스가 삭제되었으면 원본 일정도 삭제
                crud.delete_schedule(self.session, parent_schedule)

    def _are_all_instances_deleted(self, schedule: Schedule) -> bool:
        """
        반복 일정의 모든 인스턴스가 삭제되었는지 확인
        
        recurrence_end가 있는 경우에만 사용 가능합니다.
        무한 반복 일정은 확인하지 않습니다.
        
        :param schedule: 반복 일정
        :return: 모든 인스턴스가 삭제되었으면 True
        """
        if not schedule.recurrence_rule or not schedule.recurrence_end:
            return False

        # 모든 인스턴스 확장
        instances = RecurrenceCalculator.expand_recurrence(
            schedule.start_time,
            schedule.end_time,
            schedule.recurrence_rule,
            schedule.recurrence_end,
            schedule.start_time,  # 시작부터
            schedule.recurrence_end,  # 종료일까지
        )

        if not instances:
            # 인스턴스가 없으면 삭제된 것으로 간주
            return True

        # 모든 예외 인스턴스 조회 (parent_id로 필터링)
        all_exceptions = crud.get_schedule_exceptions(
            self.session,
            schedule.start_time,
            schedule.recurrence_end,
            self.owner_id,
        )
        parent_exceptions = [
            exc for exc in all_exceptions
            if exc.parent_id == schedule.id
        ]

        # 각 인스턴스가 삭제되었는지 확인
        for instance_start, instance_end in instances:
            exception = self._find_exception(
                parent_exceptions, schedule.id, instance_start
            )

            # 예외가 없거나 삭제되지 않았으면 False
            if not exception or not exception.is_deleted:
                return False

        # 모든 인스턴스가 삭제되었음
        return True

    def _filter_schedules_by_tags(
            self,
            schedules: list[Schedule],
            tag_ids: Optional[List[UUID]] = None,
            group_ids: Optional[List[UUID]] = None,
    ) -> list[Schedule]:
        """
        일정을 태그로 필터링
        
        비즈니스 로직:
        - tag_ids: AND 방식 (모든 지정 태그 포함해야 함)
        - group_ids: 해당 그룹의 태그 중 하나라도 있으면 포함
        - 둘 다 지정 시: 그룹 필터링 후 태그 필터링 적용
        
        :param schedules: 필터링할 일정 리스트
        :param tag_ids: 필터링할 태그 ID 리스트 (AND 방식)
        :param group_ids: 필터링할 그룹 ID 리스트
        :return: 필터링된 일정 리스트
        """
        if not schedules:
            return schedules

        # 그룹 ID가 지정된 경우, 해당 그룹의 태그 ID 조회
        group_tag_ids: set[UUID] = set()
        if group_ids:
            statement = select(Tag.id).where(Tag.group_id.in_(group_ids))
            group_tag_ids = set(self.session.exec(statement).all())

        # 일정별 태그 조회 (한 번에 조회하여 N+1 방지)
        schedule_ids = [s.id for s in schedules]
        statement = (
            select(ScheduleTag.schedule_id, ScheduleTag.tag_id)
            .where(ScheduleTag.schedule_id.in_(schedule_ids))
        )
        schedule_tag_rows = self.session.exec(statement).all()

        # 일정별 태그 매핑
        schedule_tag_map: dict[UUID, set[UUID]] = {}
        for schedule_id, tag_id in schedule_tag_rows:
            if schedule_id not in schedule_tag_map:
                schedule_tag_map[schedule_id] = set()
            schedule_tag_map[schedule_id].add(tag_id)

        # 가상 인스턴스(parent_id가 있는)의 경우, 부모 일정의 태그를 상속
        parent_ids = [s.parent_id for s in schedules if s.parent_id]
        if parent_ids:
            parent_statement = (
                select(ScheduleTag.schedule_id, ScheduleTag.tag_id)
                .where(ScheduleTag.schedule_id.in_(parent_ids))
            )
            parent_tag_rows = self.session.exec(parent_statement).all()

            # 부모 태그 매핑
            parent_tag_map: dict[UUID, set[UUID]] = {}
            for schedule_id, tag_id in parent_tag_rows:
                if schedule_id not in parent_tag_map:
                    parent_tag_map[schedule_id] = set()
                parent_tag_map[schedule_id].add(tag_id)

            # 가상 인스턴스에 부모 태그 상속
            for schedule in schedules:
                if schedule.parent_id and schedule.parent_id in parent_tag_map:
                    if schedule.id not in schedule_tag_map:
                        schedule_tag_map[schedule.id] = set()
                    schedule_tag_map[schedule.id].update(parent_tag_map[schedule.parent_id])

        filtered_schedules = []
        for schedule in schedules:
            schedule_tags = schedule_tag_map.get(schedule.id, set())

            # 그룹 필터링: 해당 그룹의 태그 중 하나라도 있어야 함
            if group_ids:
                if not schedule_tags.intersection(group_tag_ids):
                    continue

            # 태그 필터링: 모든 지정 태그를 포함해야 함 (AND 방식)
            if tag_ids:
                if not set(tag_ids).issubset(schedule_tags):
                    continue

            filtered_schedules.append(schedule)

        return filtered_schedules

    def get_schedule_tags(self, schedule_id: UUID) -> list[Tag]:
        """
        일정의 태그 조회
        
        :param schedule_id: 일정 ID
        :return: 태그 리스트
        """
        statement = (
            select(Tag)
            .join(ScheduleTag)
            .where(ScheduleTag.schedule_id == schedule_id)
            .order_by(Tag.name)
        )
        return list(self.session.exec(statement).all())

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

        # Schedule의 태그 ID 가져오기
        schedule_tags = self.get_schedule_tags(schedule_id)
        tag_ids = [tag.id for tag in schedule_tags] if schedule_tags else None

        # Todo 생성
        todo = self._create_todo_for_schedule(
            schedule=schedule,
            tag_group_id=tag_group_id,
            tag_ids=tag_ids,
        )

        # Schedule에 source_todo_id 설정
        schedule.source_todo_id = todo.id
        self.session.flush()
        self.session.refresh(schedule)

        return todo

    def _create_todo_for_schedule(
            self,
            schedule: Schedule,
            tag_group_id: UUID,
            tag_ids: Optional[List[UUID]] = None,
    ) -> "Todo":
        """
        Schedule에서 Todo 생성 (내부 헬퍼 메서드)
        
        Schedule의 정보를 기반으로 Todo를 생성합니다.
        deadline은 Schedule의 start_time으로 설정합니다.
        
        :param schedule: Schedule 객체
        :param tag_group_id: Todo가 속할 그룹 ID
        :param tag_ids: 태그 ID 리스트 (선택)
        :return: 생성된 Todo
        """
        from app.crud import todo as todo_crud
        from app.models.todo import Todo as TodoModel
        from app.domain.todo.enums import TodoStatus

        # Todo 모델 생성 (deadline = schedule.start_time)
        todo = TodoModel(
            owner_id=self.owner_id,
            title=schedule.title,
            description=schedule.description,
            deadline=schedule.start_time,  # Schedule의 start_time을 deadline으로
            tag_group_id=tag_group_id,
            parent_id=None,
            status=TodoStatus.SCHEDULED,  # Schedule이 있으므로 SCHEDULED
        )
        todo = todo_crud.create_todo(self.session, todo)

        # 태그 설정
        if tag_ids:
            from app.domain.tag.service import TagService
            tag_service = TagService(self.session, self.current_user)
            tag_service.set_todo_tags(todo.id, tag_ids)
            self.session.refresh(todo)

        return todo
