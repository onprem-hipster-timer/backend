"""
Schedule Service

FastAPI Best Practices:
- Service는 비즈니스 로직을 담당
- CRUD 함수를 직접 사용 (Repository 패턴 제거)
- Domain Exception을 발생시켜 비즈니스 규칙 위반 표현
- 모든 datetime을 UTC naive로 변환하여 저장 (모든 DB 구조에서 일관성 보장)
"""
from datetime import datetime
from uuid import UUID

from sqlmodel import Session

from app.crud import schedule as crud
from app.domain.schedule.exceptions import ScheduleNotFoundError
from app.domain.schedule.model import Schedule
from app.domain.schedule.schema.dto import ScheduleCreate, ScheduleUpdate
from app.utils.datetime_utils import ensure_utc_naive


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
        
        :param data: 일정 생성 데이터
        :return: 생성된 일정
        """
        # UTC naive datetime으로 변환하여 저장
        create_data = ScheduleCreate(
            title=data.title,
            description=data.description,
            start_time=ensure_utc_naive(data.start_time),
            end_time=ensure_utc_naive(data.end_time),
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
        날짜 범위로 일정 조회
        
        비즈니스 로직:
        - 모든 datetime을 UTC naive로 변환하여 조회
        - 모든 DB 구조에서 일관성 보장
        
        :param start_date: 시작 날짜
        :param end_date: 종료 날짜
        :return: 해당 날짜 범위와 겹치는 모든 일정
        """
        # UTC naive datetime으로 변환하여 조회
        start_date_utc = ensure_utc_naive(start_date)
        end_date_utc = ensure_utc_naive(end_date)
        
        return crud.get_schedules_by_date_range(self.session, start_date_utc, end_date_utc)

    def update_schedule(
            self,
            schedule_id: UUID,
            data: ScheduleUpdate,
    ) -> Schedule:
        """
        일정 업데이트
        
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
        
        # 변환된 dict로 ScheduleUpdate 재생성
        update_data = ScheduleUpdate(**update_dict)

        return crud.update_schedule(self.session, schedule, update_data)

    def delete_schedule(self, schedule_id: UUID) -> None:
        """
        일정 삭제
        
        :param schedule_id: 일정 ID
        :raises ScheduleNotFoundError: 일정을 찾을 수 없는 경우
        """
        schedule = crud.get_schedule(self.session, schedule_id)
        if not schedule:
            raise ScheduleNotFoundError()

        crud.delete_schedule(self.session, schedule)
