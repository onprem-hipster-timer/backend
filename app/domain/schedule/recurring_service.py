"""
Recurring Schedule Service

반복 일정 인스턴스의 생성, 수정, 삭제를 담당합니다.
"""
from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Session

from app.crud import schedule as crud
from app.domain.dateutil.service import ensure_utc_naive, is_datetime_within_tolerance
from app.domain.schedule.exceptions import (
    ScheduleNotFoundError,
    RecurringScheduleError,
)
from app.domain.schedule.model import Schedule
from app.domain.schedule.schema.dto import ScheduleUpdate
from app.models.schedule import ScheduleException
from app.utils.recurrence import RecurrenceCalculator


class RecurringScheduleService:
    """
    반복 일정 인스턴스 관리 서비스

    - 가상 인스턴스 생성/조회
    - 반복 인스턴스 수정/삭제 (ScheduleException 기반)
    - 전체 인스턴스 삭제 여부 판정
    """

    def __init__(self, session: Session, owner_id: str):
        self.session = session
        self.owner_id = owner_id

    def create_virtual_instance(
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

    def find_exception(
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

    def update_recurring_instance(
            self,
            parent_id: UUID,
            instance_start: datetime,
            data: ScheduleUpdate,
            current_user,
    ) -> Schedule:
        """
        반복 일정의 특정 인스턴스 수정

        가상 인스턴스를 수정하면 ScheduleException을 생성하거나 업데이트합니다.
        프론트엔드는 parent_id와 instance_start를 함께 전송합니다.

        :param parent_id: 원본 일정 ID
        :param instance_start: 인스턴스 시작 시간
        :param data: 업데이트 데이터
        :param current_user: 현재 사용자 (TagService 인스턴스화에 필요)
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

        # 업데이트 데이터 준비 (datetime은 DTO에서 UTC naive로 변환됨, MISSING 필드는 자동 제외)
        update_dict = data.model_dump()

        # 태그 ID 추출 (별도 처리)
        tag_ids = update_dict.pop('tag_ids', None)

        # 예외 인스턴스 생성 또는 업데이트
        if existing_exception:
            # 기존 예외 인스턴스 업데이트
            if existing_exception.is_deleted:
                existing_exception.is_deleted = False

            crud.update_schedule_exception(self.session, existing_exception, update_dict)

            # 태그 업데이트 (tag_ids가 설정된 경우에만)
            if tag_ids is not None:
                from app.domain.tag.service import TagService
                tag_service = TagService(self.session, current_user)
                tag_service.set_schedule_exception_tags(existing_exception.id, tag_ids)

            # 가상 인스턴스 반환
            instance_end = existing_exception.end_time or (
                    instance_start_utc + (parent_schedule.end_time - parent_schedule.start_time)
            )
            return self.create_virtual_instance(
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
                tag_service = TagService(self.session, current_user)
                tag_service.set_schedule_exception_tags(exception.id, tag_ids)

            # 가상 인스턴스 반환
            instance_end = exception.end_time or (
                    instance_start_utc + (parent_schedule.end_time - parent_schedule.start_time)
            )
            return self.create_virtual_instance(
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
            exception = self.find_exception(
                parent_exceptions, schedule.id, instance_start
            )

            # 예외가 없거나 삭제되지 않았으면 False
            if not exception or not exception.is_deleted:
                return False

        # 모든 인스턴스가 삭제되었음
        return True
