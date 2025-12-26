"""
Schedule Repository

아키텍처 원칙:
- Repository는 데이터 접근 로직만 담당
- 비즈니스 로직은 Service 계층에서 처리
- Context Manager 패턴으로 세션 관리
"""
from datetime import datetime
from typing import Optional
from uuid import UUID
from sqlmodel import Session, select

from app.domain.schedule.model import Schedule
from app.domain.schedule.schema.dto import ScheduleCreate, ScheduleUpdate


class ScheduleRepository:
    """Schedule Repository - 데이터 접근 로직"""
    
    def __init__(self, session: Session):
        self.session = session
    
    def create(self, data: ScheduleCreate) -> Schedule:
        """
        새 Schedule을 DB에 생성합니다.
        
        :param data: Schedule 생성 데이터
        :return: 생성된 Schedule
        """
        schedule = Schedule.model_validate(data)
        self.session.add(schedule)
        self.session.commit()
        self.session.refresh(schedule)
        return schedule
    
    def get_by_id(self, schedule_id: UUID) -> Optional[Schedule]:
        """
        ID로 Schedule 조회
        
        :param schedule_id: Schedule ID
        :return: Schedule 또는 None
        """
        return self.session.get(Schedule, schedule_id)
    
    def get_all(self) -> list[Schedule]:
        """
        모든 Schedule 조회
        
        :return: Schedule 리스트
        """
        statement = select(Schedule)
        results = self.session.exec(statement)
        return results.all()
    
    def get_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> list[Schedule]:
        """
        날짜 범위로 Schedule 조회
        
        :param start_date: 시작 날짜 (이 날짜 이후에 시작하는 일정 포함)
        :param end_date: 종료 날짜 (이 날짜 이전에 종료하는 일정 포함)
        :return: 해당 날짜 범위와 겹치는 모든 일정
        """
        # 일정이 주어진 날짜 범위와 겹치는 경우를 조회
        # 일정의 start_time <= end_date AND 일정의 end_time >= start_date
        statement = (
            select(Schedule)
            .where(Schedule.start_time <= end_date)
            .where(Schedule.end_time >= start_date)
            .order_by(Schedule.start_time)
        )
        results = self.session.exec(statement)
        return results.all()
    
    def update(self, schedule: Schedule, data: ScheduleUpdate) -> Schedule:
        """
        Schedule 업데이트
        
        :param schedule: 업데이트할 Schedule
        :param data: 업데이트 데이터
        :return: 업데이트된 Schedule
        """
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(schedule, field, value)
        
        self.session.commit()
        self.session.refresh(schedule)
        return schedule
    
    def delete(self, schedule: Schedule) -> None:
        """
        Schedule 삭제
        
        :param schedule: 삭제할 Schedule
        """
        self.session.delete(schedule)
        self.session.commit()

