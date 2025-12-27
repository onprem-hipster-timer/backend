"""
Schedule Service

FastAPI Best Practices:
- Service는 비즈니스 로직을 담당
- CRUD 함수를 직접 사용 (Repository 패턴 제거)
- Domain Exception을 발생시켜 비즈니스 규칙 위반 표현
- 모든 datetime을 UTC naive로 변환하여 저장 (모든 DB 구조에서 일관성 보장)
"""
from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Session

from app.crud import schedule as crud
from app.domain.schedule.exceptions import (
    ScheduleNotFoundError,
    InvalidRecurrenceRuleError,
    InvalidRecurrenceEndError,
    RecurringScheduleError,
)
from app.domain.schedule.model import Schedule
from app.domain.schedule.schema.dto import ScheduleCreate, ScheduleUpdate
from app.models.schedule import ScheduleException
from app.utils.datetime_utils import ensure_utc_naive, is_datetime_within_tolerance
from app.utils.recurrence import RecurrenceCalculator


class ScheduleService:
    """
    Schedule Service - 비즈니스 로직
    
    FastAPI Best Practices:
    - Repository 패턴 제거, CRUD 함수 직접 사용
    - Session을 받아서 CRUD 함수 호출
    - 모든 datetime을 UTC naive로 변환하여 저장 (모든 DB 구조에서 일관성 보장)
    """

    def __init__(self, session: Session):
        self.session = session

    def create_schedule(self, data: ScheduleCreate) -> Schedule:
        """
        일정 생성
        
        비즈니스 로직:
        - 모든 datetime을 UTC naive로 변환하여 저장
        - 모든 DB 구조에서 일관성 보장
        - 반복 일정 필드도 함께 저장
        - RRULE 검증
        
        :param data: 일정 생성 데이터
        :return: 생성된 일정
        :raises InvalidRecurrenceRuleError: RRULE 형식이 잘못된 경우
        :raises InvalidRecurrenceEndError: 반복 종료일이 시작일 이전인 경우
        """
        start_time_utc = ensure_utc_naive(data.start_time)
        end_time_utc = ensure_utc_naive(data.end_time)
        recurrence_end_utc = ensure_utc_naive(data.recurrence_end) if data.recurrence_end else None

        # 반복 일정 검증
        if data.recurrence_rule:
            if not RecurrenceCalculator.is_valid_rrule(data.recurrence_rule):
                raise InvalidRecurrenceRuleError()
            
            if recurrence_end_utc and recurrence_end_utc < start_time_utc:
                raise InvalidRecurrenceEndError()

        # UTC naive datetime으로 변환하여 저장
        create_data = ScheduleCreate(
            title=data.title,
            description=data.description,
            start_time=start_time_utc,
            end_time=end_time_utc,
            recurrence_rule=data.recurrence_rule,
            recurrence_end=recurrence_end_utc,
        )

        return crud.create_schedule(self.session, create_data)

    def get_schedule(self, schedule_id: UUID) -> Schedule:
        """
        일정 조회
        
        :param schedule_id: 일정 ID
        :return: 일정
        :raises ScheduleNotFoundError: 일정을 찾을 수 없는 경우
        """
        schedule = crud.get_schedule(self.session, schedule_id)
        if not schedule:
            raise ScheduleNotFoundError()
        return schedule

    def get_all_schedules(self) -> list[Schedule]:
        """
        모든 일정 조회
        
        :return: 일정 리스트
        """
        return crud.get_schedules(self.session)

    def get_schedules_by_date_range(
            self,
            start_date: datetime,
            end_date: datetime,
    ) -> list[Schedule]:
        """
        날짜 범위로 일정 조회 (반복 일정 포함)
        
        비즈니스 로직:
        - 모든 datetime을 UTC naive로 변환하여 조회
        - 반복 일정은 가상 인스턴스로 확장하여 반환
        - 예외 인스턴스 처리 (삭제/수정된 인스턴스)
        
        :param start_date: 시작 날짜
        :param end_date: 종료 날짜
        :return: 해당 날짜 범위와 겹치는 모든 일정 (가상 인스턴스 포함)
        """
        # UTC naive datetime으로 변환하여 조회
        start_date_utc = ensure_utc_naive(start_date)
        end_date_utc = ensure_utc_naive(end_date)

        # 1. 일반 일정 조회 (반복 일정 제외)
        regular_schedules = crud.get_schedules_by_date_range(
            self.session, start_date_utc, end_date_utc
        )
        # 반복 일정이 아닌 것만 필터링
        regular_schedules = [
            s for s in regular_schedules 
            if not s.recurrence_rule
        ]

        # 2. 반복 일정 조회 (원본만)
        recurring_schedules = crud.get_recurring_schedules(
            self.session, start_date_utc, end_date_utc
        )

        # 3. 예외 인스턴스 조회
        exceptions = crud.get_schedule_exceptions(
            self.session, start_date_utc, end_date_utc
        )

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
                exception = self._find_exception(
                    exceptions, schedule.id, instance_start
                )

                if exception and exception.is_deleted:
                    continue  # 삭제된 인스턴스는 제외

                # 가상 인스턴스 생성
                virtual_schedule = self._create_virtual_instance(
                    schedule, instance_start, instance_end, exception
                )
                virtual_instances.append(virtual_schedule)

        # 5. 일반 일정 + 가상 인스턴스 합치기
        all_schedules = list(regular_schedules) + virtual_instances

        # 6. 시간순 정렬
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
        - 모든 datetime을 UTC naive로 변환하여 저장
        - 모든 DB 구조에서 일관성 보장
        
        :param schedule_id: 일정 ID
        :param data: 업데이트 데이터
        :return: 업데이트된 일정
        :raises ScheduleNotFoundError: 일정을 찾을 수 없는 경우
        """
        schedule = crud.get_schedule(self.session, schedule_id)
        if not schedule:
            raise ScheduleNotFoundError()

        # 설정된 필드만 가져오기 (exclude_unset=True)
        update_dict = data.model_dump(exclude_unset=True)

        # datetime 필드가 설정되어 있으면 UTC naive로 변환
        if 'start_time' in update_dict:
            update_dict['start_time'] = ensure_utc_naive(update_dict['start_time'])
        if 'end_time' in update_dict:
            update_dict['end_time'] = ensure_utc_naive(update_dict['end_time'])
        if 'recurrence_end' in update_dict and update_dict['recurrence_end']:
            update_dict['recurrence_end'] = ensure_utc_naive(update_dict['recurrence_end'])

        # 변환된 dict로 ScheduleUpdate 재생성
        update_data = ScheduleUpdate(**update_dict)

        return crud.update_schedule(self.session, schedule, update_data)

    def delete_schedule(self, schedule_id: UUID) -> None:
        """
        일정 삭제
        
        비즈니스 로직:
        - DB 레벨 CASCADE DELETE로 관련 예외 인스턴스 자동 삭제
        - 모든 DB 구조에서 일관성 보장
        
        :param schedule_id: 일정 ID
        :raises ScheduleNotFoundError: 일정을 찾을 수 없는 경우
        """
        schedule = crud.get_schedule(self.session, schedule_id)
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
        parent_schedule = crud.get_schedule(self.session, parent_id)
        if not parent_schedule:
            raise ScheduleNotFoundError()
        
        if not parent_schedule.recurrence_rule:
            raise RecurringScheduleError()
        
        # instance_start를 UTC naive로 변환
        instance_start_utc = ensure_utc_naive(instance_start)
        
        # 기존 예외 인스턴스 조회
        existing_exception = crud.get_schedule_exception_by_date(
            self.session, parent_id, instance_start_utc
        )
        
        # 업데이트 데이터 준비
        update_dict = data.model_dump(exclude_unset=True)
        
        # datetime 필드 변환
        if 'start_time' in update_dict:
            update_dict['start_time'] = ensure_utc_naive(update_dict['start_time'])
        if 'end_time' in update_dict:
            update_dict['end_time'] = ensure_utc_naive(update_dict['end_time'])
        
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
                is_deleted=False,
                title=update_dict.get('title'),
                description=update_dict.get('description'),
                start_time=update_dict.get('start_time'),
                end_time=update_dict.get('end_time'),
            )
            
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
        parent_schedule = crud.get_schedule(self.session, parent_id)
        if not parent_schedule:
            raise ScheduleNotFoundError()
        
        if not parent_schedule.recurrence_rule:
            raise RecurringScheduleError()
        
        # instance_start를 UTC naive로 변환
        instance_start_utc = ensure_utc_naive(instance_start)
        
        # 기존 예외 인스턴스 조회
        existing_exception = crud.get_schedule_exception_by_date(
            self.session, parent_id, instance_start_utc
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
