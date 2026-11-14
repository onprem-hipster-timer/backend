"""
Schedule Query Service

날짜 범위 조회 및 태그 필터링을 담당합니다.
"""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlmodel import Session, select

from app.crud import schedule as crud
from app.domain.dateutil.service import ensure_utc_naive, is_datetime_within_tolerance
from app.domain.schedule.model import Schedule
from app.domain.schedule.recurring_service import RecurringScheduleService
from app.models.schedule import ScheduleException
from app.models.tag import Tag, ScheduleTag
from app.utils.recurrence import RecurrenceCalculator


class ScheduleQueryService:
    """
    일정 조회 및 태그 필터링 서비스

    - 날짜 범위 조회 (반복 일정 확장 포함)
    - 태그 기반 필터링 (AND/OR 방식)
    """

    def __init__(self, session: Session, owner_id: str):
        self.session = session
        self.owner_id = owner_id
        self._recurring = RecurringScheduleService(session, owner_id)

    def get_all_schedules_with_tag_filter(
            self,
            tag_ids: Optional[List[UUID]] = None,
            group_ids: Optional[List[UUID]] = None,
    ) -> list[Schedule]:
        """
        모든 일정 조회 (태그 필터링 지원)

        :param tag_ids: 필터링할 태그 ID 리스트 (AND 방식)
        :param group_ids: 필터링할 그룹 ID 리스트
        :return: 필터링된 일정 리스트
        """
        all_schedules = crud.get_schedules(self.session, self.owner_id)

        # 태그 필터링 적용
        if tag_ids or group_ids:
            return self.filter_schedules_by_tags(all_schedules, tag_ids, group_ids)

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

        # 3. 예외 인스턴스 조회
        exceptions = crud.get_schedule_exceptions(
            self.session, start_date_utc, end_date_utc, self.owner_id
        )

        # 4. 반복 일정 확장 + 일반 일정 합치기 (시간순 정렬)
        all_schedules = self.expand_in_range(
            list(regular_schedules) + list(recurring_schedules),
            exceptions,
            start_date_utc,
            end_date_utc,
        )

        # 5. 태그 필터링 적용
        if tag_ids or group_ids:
            all_schedules = self.filter_schedules_by_tags(
                all_schedules, tag_ids, group_ids
            )

        return all_schedules

    def get_shared_schedules_by_date_range(
            self,
            shared_schedules: list[Schedule],
            start_date: datetime,
            end_date: datetime,
    ) -> list[Schedule]:
        """
        접근 가능한 공유 일정을 날짜 범위로 조회 (반복 일정은 가상 인스턴스로 확장)

        예외 인스턴스는 넘겨받은 반복 일정의 것만 배치로 조회한다.

        :param shared_schedules: 접근 권한이 확인된 타인 소유 일정
        :param start_date: 시작 날짜
        :param end_date: 종료 날짜
        :return: 해당 날짜 범위와 겹치는 일정 (가상 인스턴스 포함, 시간순)
        """
        start_date_utc = ensure_utc_naive(start_date)
        end_date_utc = ensure_utc_naive(end_date)

        recurring_ids = [s.id for s in shared_schedules if s.recurrence_rule]
        exceptions = crud.get_schedule_exceptions_by_parent_ids(
            self.session, recurring_ids, start_date_utc, end_date_utc
        )
        return self.expand_in_range(shared_schedules, exceptions, start_date_utc, end_date_utc)

    def expand_in_range(
            self,
            schedules: list[Schedule],
            exceptions: list[ScheduleException],
            start_date_utc: datetime,
            end_date_utc: datetime,
    ) -> list[Schedule]:
        """
        일정 목록을 날짜 범위 안의 항목으로 펼친다

        - 일반 일정: 범위와 겹치면 그대로 포함
        - 반복 일정: 범위 안의 회차를 가상 인스턴스로 확장 (삭제된 회차 제외, 수정된 회차는 예외 값)

        :param schedules: 일정 리스트 (일반 + 반복 원본)
        :param exceptions: 반복 일정들의 예외 인스턴스
        :param start_date_utc: 시작 날짜 (UTC naive)
        :param end_date_utc: 종료 날짜 (UTC naive)
        :return: 범위와 겹치는 일정과 가상 인스턴스 (시간순)
        """
        regular_schedules = [
            s for s in schedules
            if not s.recurrence_rule
            and s.start_time <= end_date_utc and s.end_time >= start_date_utc
        ]
        recurring_schedules = [s for s in schedules if s.recurrence_rule]

        exception_dict, exceptions_by_parent = self._index_exceptions(exceptions)

        # 반복 일정을 가상 인스턴스로 확장
        virtual_instances = []
        for schedule in recurring_schedules:
            virtual_instances.extend(
                self._expand_recurring(
                    schedule, exception_dict, exceptions_by_parent, start_date_utc, end_date_utc
                )
            )

        # 일반 일정 + 가상 인스턴스 합치기 (시간순 정렬)
        return sorted(regular_schedules + virtual_instances, key=lambda s: s.start_time)

    @staticmethod
    def _index_exceptions(
            exceptions: list[ScheduleException],
    ) -> tuple[
        dict[tuple[UUID, datetime], ScheduleException],
        dict[UUID, list[ScheduleException]],
    ]:
        """예외를 한 번만 순회하여 (parent_id, 날짜) 매칭용 dict와 parent별 그룹을 만든다"""
        exception_dict = {}
        exceptions_by_parent = {}
        for exc in exceptions:
            # 정확한 매칭용 딕셔너리
            exception_dict[(exc.parent_id, exc.exception_date)] = exc

            # parent별 그룹화 (허용 오차 검색용)
            if exc.parent_id not in exceptions_by_parent:
                exceptions_by_parent[exc.parent_id] = []
            exceptions_by_parent[exc.parent_id].append(exc)
        return exception_dict, exceptions_by_parent

    def _expand_recurring(
            self,
            schedule: Schedule,
            exception_dict: dict[tuple[UUID, datetime], ScheduleException],
            exceptions_by_parent: dict[UUID, list[ScheduleException]],
            start_date_utc: datetime,
            end_date_utc: datetime,
    ) -> list[Schedule]:
        """반복 일정 하나를 범위 안의 가상 인스턴스로 확장한다 (삭제된 회차 제외)"""
        instances = RecurrenceCalculator.expand_recurrence(
            schedule.start_time,
            schedule.end_time,
            schedule.recurrence_rule,
            schedule.recurrence_end,
            start_date_utc,
            end_date_utc,
        )

        virtual_instances = []
        for instance_start, instance_end in instances:
            exception = self._find_exception(
                schedule.id, instance_start, exception_dict, exceptions_by_parent
            )
            if exception and exception.is_deleted:
                continue  # 삭제된 인스턴스는 제외

            # 가상 인스턴스 생성
            virtual_instances.append(
                self._recurring.create_virtual_instance(
                    schedule, instance_start, instance_end, exception
                )
            )
        return virtual_instances

    @staticmethod
    def _find_exception(
            parent_id: UUID,
            instance_start: datetime,
            exception_dict: dict[tuple[UUID, datetime], ScheduleException],
            exceptions_by_parent: dict[UUID, list[ScheduleException]],
    ) -> Optional[ScheduleException]:
        """회차의 예외를 찾는다 (정확히 매칭되지 않으면 해당 parent의 예외에서 시간 허용 오차 검색)"""
        exception = exception_dict.get((parent_id, instance_start))
        if exception is not None:
            return exception
        for exc in exceptions_by_parent.get(parent_id, []):
            if is_datetime_within_tolerance(exc.exception_date, instance_start):
                return exc
        return None

    def filter_schedules_by_tags(
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
