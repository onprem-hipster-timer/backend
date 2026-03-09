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
                virtual_schedule = self._recurring.create_virtual_instance(
                    schedule, instance_start, instance_end, exception
                )
                virtual_instances.append(virtual_schedule)

        # 5. 일반 일정 + 가상 인스턴스 합치기
        all_schedules = list(regular_schedules) + virtual_instances

        # 6. 태그 필터링 적용
        if tag_ids or group_ids:
            all_schedules = self.filter_schedules_by_tags(
                all_schedules, tag_ids, group_ids
            )

        # 7. 시간순 정렬
        return sorted(all_schedules, key=lambda s: s.start_time)

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
