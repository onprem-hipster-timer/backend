"""
Schedule Domain GraphQL Query

아키텍처 원칙:
- Domain이 자신의 GraphQL Query를 정의
- Resolver는 thin하게, 실제 작업은 Domain Service에 위임
"""
from datetime import date, datetime, timedelta
from typing import List, TypedDict

import strawberry
from sqlmodel import Session
from strawberry.types import Info

from app.domain.schedule.schema.types import Event, Day, Calendar
from app.domain.schedule.service import ScheduleService


class GraphQLContext(TypedDict):
    """
    GraphQL 컨텍스트 타입 정의
    
    최신 패턴: dict 기반 context 사용
    """
    request: object  # FastAPI Request
    session: Session  # DB 세션


# GraphQLContext는 dict로 대체 (최신 패턴)
# router.py에서 context_getter가 dict를 반환하도록 변경


@strawberry.type
class ScheduleQuery:
    """
    Schedule Domain GraphQL Query
    
    아키텍처 원칙:
    - Domain이 자신의 GraphQL Query를 정의
    - Resolver는 thin하게, 실제 작업은 Domain Service에 위임
    """

    @strawberry.field
    async def calendar(
            self,
            info: Info[GraphQLContext, None],
            start_date: date,
            end_date: date,
    ) -> Calendar:
        """
        날짜 범위로 캘린더 데이터를 조회합니다.
        
        아키텍처 원칙 준수:
        - Resolver는 thin하게 유지
        - 실제 데이터 조회는 Domain Service에 위임
        - N+1 문제 방지: 날짜 범위로 한 번에 조회
        
        주간 뷰(7일) 또는 월간 뷰(30일) 모두 지원합니다.
        모든 필요한 데이터를 단일 GraphQL 쿼리로 가져옵니다.
        
        Bug Fix: Generator cleanup 보장
        - try-finally를 통해 세션 Generator를 명시적으로 정리
        - 요청 종료 시 세션 정리 보장
        
        :param info: GraphQL info 객체 (컨텍스트 접근용)
        :param start_date: 시작 날짜
        :param end_date: 종료 날짜
        :return: Calendar 객체 (days와 events 포함)
        """
        context: GraphQLContext = info.context
        session: Session = context["session"]
        session_gen = context.get("_session_gen")  # Generator 참조

        try:
            # 날짜 범위를 datetime으로 변환 (하루의 시작과 끝)
            start_datetime = datetime.combine(start_date, datetime.min.time())
            end_datetime = datetime.combine(end_date, datetime.max.time())

            # ✅ Domain Service 사용 (N+1 문제 방지)
            # FastAPI Best Practices: Service는 session을 받아서 CRUD 직접 사용
            service = ScheduleService(session)
            schedules = service.get_schedules_by_date_range(
                start_datetime,
                end_datetime,
            )

            # 날짜별로 일정을 그룹화 (메모리에서 처리)
            events_by_date: dict[date, List[Event]] = {}

            # 모든 날짜 초기화 (빈 리스트로)
            current_date = start_date
            while current_date <= end_date:
                events_by_date[current_date] = []
                current_date += timedelta(days=1)

            # 일정을 날짜별로 분류
            for schedule in schedules:
                event = Event.from_schedule(schedule)

                # 일정이 겹치는 모든 날짜에 추가
                schedule_start_date = schedule.start_time.date()
                schedule_end_date = schedule.end_time.date()

                current_date = max(schedule_start_date, start_date)
                end_date_inclusive = min(schedule_end_date, end_date)

                while current_date <= end_date_inclusive:
                    if current_date in events_by_date:
                        events_by_date[current_date].append(event)
                    current_date += timedelta(days=1)

            # Day 객체 리스트 생성
            days = [
                Day(date=date_key, events=events)
                for date_key, events in sorted(events_by_date.items())
            ]

            return Calendar(days=days)
        finally:
            # Generator cleanup 보장 - 세션 정리
            if session_gen:
                try:
                    next(session_gen, None)  # Generator 종료 (기본값 제공으로 StopIteration 발생 안 함)
                except Exception:
                    # Generator 종료 중 발생할 수 있는 모든 예외 무시
                    # (예: Generator가 이미 닫혔거나, 세션 정리 중 오류)
                    pass


# GraphQL Root Schema 생성
@strawberry.type
class Query(ScheduleQuery):
    """
    GraphQL Root Query
    
    여러 도메인의 Query를 통합합니다.
    현재는 Schedule 도메인만 포함되어 있지만,
    향후 다른 도메인(예: User, Order 등)의 Query도 추가 가능합니다.
    """
    pass


# GraphQL 스키마 export
from app.core.error_handlers import GraphQLErrorHandlingExtension

schema = strawberry.Schema(
    query=Query,
    extensions=[GraphQLErrorHandlingExtension],
)
