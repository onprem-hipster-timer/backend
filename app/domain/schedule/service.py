"""
Schedule Service

FastAPI Best Practices:
- Service는 비즈니스 로직을 담당
- CRUD 함수를 직접 사용 (Repository 패턴 제거)
- Domain Exception을 발생시켜 비즈니스 규칙 위반 표현
"""
from datetime import datetime
from uuid import UUID
from sqlmodel import Session

from app.crud import schedule as crud
from app.domain.schedule.model import Schedule
from app.domain.schedule.exceptions import ScheduleNotFoundError
from app.domain.schedule.schema.dto import ScheduleCreate, ScheduleUpdate


class ScheduleService:
    """
    Schedule Service - 비즈니스 로직
    
    FastAPI Best Practices:
    - Repository 패턴 제거, CRUD 함수 직접 사용
    - Session을 받아서 CRUD 함수 호출
    """
    
    def __init__(self, session: Session):
        self.session = session
    
    def create_schedule(self, data: ScheduleCreate) -> Schedule:
        """
        일정 생성
        
        :param data: 일정 생성 데이터
        :return: 생성된 일정
        """
        # 비즈니스 로직: 시간 검증은 Pydantic validator에서 처리
        return crud.create_schedule(self.session, data)
    
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
        
        :param start_date: 시작 날짜
        :param end_date: 종료 날짜
        :return: 해당 날짜 범위와 겹치는 모든 일정
        """
        return crud.get_schedules_by_date_range(self.session, start_date, end_date)
    
    def update_schedule(
        self,
        schedule_id: UUID,
        data: ScheduleUpdate,
    ) -> Schedule:
        """
        일정 업데이트
        
        :param schedule_id: 일정 ID
        :param data: 업데이트 데이터
        :return: 업데이트된 일정
        :raises ScheduleNotFoundError: 일정을 찾을 수 없는 경우
        """
        schedule = crud.get_schedule(self.session, schedule_id)
        if not schedule:
            raise ScheduleNotFoundError()
        
        return crud.update_schedule(self.session, schedule, data)
    
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

