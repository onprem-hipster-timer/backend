"""
Schedule Service

아키텍처 원칙:
- Service는 비즈니스 로직을 담당
- Repository를 통해 데이터 접근
- Domain Exception을 발생시켜 비즈니스 규칙 위반 표현
"""
from datetime import datetime
from uuid import UUID

from app.domain.schedule.repository import ScheduleRepository
from app.domain.schedule.model import Schedule
from app.domain.schedule.exceptions import ScheduleNotFoundError
from app.domain.schedule.schema.dto import ScheduleCreate, ScheduleUpdate


class ScheduleService:
    """Schedule Service - 비즈니스 로직"""
    
    def __init__(self, repository: ScheduleRepository):
        self.repository = repository
    
    def create_schedule(self, data: ScheduleCreate) -> Schedule:
        """
        일정 생성
        
        :param data: 일정 생성 데이터
        :return: 생성된 일정
        """
        # 비즈니스 로직: 시간 검증은 Pydantic validator에서 처리
        return self.repository.create(data)
    
    def get_schedule(self, schedule_id: UUID) -> Schedule:
        """
        일정 조회
        
        :param schedule_id: 일정 ID
        :return: 일정
        :raises ScheduleNotFoundError: 일정을 찾을 수 없는 경우
        """
        schedule = self.repository.get_by_id(schedule_id)
        if not schedule:
            raise ScheduleNotFoundError()
        return schedule
    
    def get_all_schedules(self) -> list[Schedule]:
        """
        모든 일정 조회
        
        :return: 일정 리스트
        """
        return self.repository.get_all()
    
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
        return self.repository.get_by_date_range(start_date, end_date)
    
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
        schedule = self.repository.get_by_id(schedule_id)
        if not schedule:
            raise ScheduleNotFoundError()
        
        return self.repository.update(schedule, data)
    
    def delete_schedule(self, schedule_id: UUID) -> None:
        """
        일정 삭제
        
        :param schedule_id: 일정 ID
        :raises ScheduleNotFoundError: 일정을 찾을 수 없는 경우
        """
        schedule = self.repository.get_by_id(schedule_id)
        if not schedule:
            raise ScheduleNotFoundError()
        
        self.repository.delete(schedule)

