"""
반복 일정 계산 유틸리티

RRULE 기반으로 반복 일정의 가상 인스턴스를 생성합니다.
"""
from datetime import datetime
from typing import List, Optional

from dateutil.rrule import rrulestr

from app.utils.datetime_utils import format_datetime_for_rrule


class RecurrenceCalculator:
    """반복 일정 계산 유틸리티"""

    @staticmethod
    def expand_recurrence(
            start_time: datetime,
            end_time: datetime,
            recurrence_rule: str,
            recurrence_end: Optional[datetime],
            query_start: datetime,
            query_end: datetime,
    ) -> List[tuple[datetime, datetime]]:
        """
        반복 일정을 가상 인스턴스로 확장
        
        :param start_time: 원본 일정 시작 시간
        :param end_time: 원본 일정 종료 시간
        :param recurrence_rule: RRULE 형식의 반복 규칙 (예: "FREQ=WEEKLY;BYDAY=MO")
        :param recurrence_end: 반복 종료일 (None이면 무한 반복)
        :param query_start: 조회 시작 날짜
        :param query_end: 조회 종료 날짜
        :return: [(start_time, end_time), ...] 리스트
        """
        if not recurrence_rule:
            # 반복 일정이 아니면 원본만 반환
            if start_time <= query_end and end_time >= query_start:
                return [(start_time, end_time)]
            return []

        # 일정의 지속 시간 계산
        duration = end_time - start_time

        # RRULE 파싱 및 계산
        # until 파라미터가 있으면 추가
        rrule_str = recurrence_rule
        if recurrence_end:
            # RRULE에 UNTIL이 없으면 추가
            if "UNTIL" not in rrule_str.upper():
                rrule_str = f"{rrule_str};UNTIL={format_datetime_for_rrule(recurrence_end)}"

        try:
            rrule_obj = rrulestr(
                rrule_str,
                dtstart=start_time,
            )
        except Exception:
            # RRULE 파싱 실패 시 원본만 반환
            if start_time <= query_end and end_time >= query_start:
                return [(start_time, end_time)]
            return []

        # 쿼리 범위 내의 인스턴스만 생성
        instances = []
        for instance_start in rrule_obj:
            # 조회 범위를 벗어나면 중단
            if instance_start > query_end:
                break

            # 조회 범위 이전이면 스킵
            instance_end = instance_start + duration
            if instance_end < query_start:
                continue

            instances.append((instance_start, instance_end))

        return instances

    @staticmethod
    def is_valid_rrule(rrule_str: str) -> bool:
        """
        RRULE 문자열이 유효한지 검증
        
        :param rrule_str: RRULE 형식의 문자열
        :return: 유효하면 True, 아니면 False
        """
        if not rrule_str:
            return False

        try:
            # 임시 datetime으로 파싱 테스트
            test_start = datetime(2024, 1, 1, 10, 0, 0)
            rrulestr(rrule_str, dtstart=test_start)
            return True
        except Exception:
            return False
