"""
Timer Service

FastAPI Best Practices:
- Service는 비즈니스 로직을 담당
- CRUD 함수를 직접 사용 (Repository 패턴 제거)
- Domain Exception을 발생시켜 비즈니스 규칙 위반 표현
- 모든 datetime을 UTC naive로 변환하여 저장
"""
from datetime import datetime, UTC
from uuid import UUID

from sqlmodel import Session

from app.core.constants import TimerStatus
from app.crud import timer as crud, schedule as schedule_crud
from app.domain.dateutil.service import ensure_utc_naive
from app.domain.schedule.exceptions import ScheduleNotFoundError
from app.domain.timer.exceptions import (
    TimerNotFoundError,
    InvalidTimerStatusError,
)
from app.domain.timer.model import TimerSession
from app.domain.timer.schema.dto import TimerCreate, TimerUpdate


class TimerService:
    """
    Timer Service - 비즈니스 로직
    
    FastAPI Best Practices:
    - Repository 패턴 제거, CRUD 함수 직접 사용
    - Session을 받아서 CRUD 함수 호출
    - 모든 datetime을 UTC naive로 변환하여 저장
    """

    def __init__(self, session: Session):
        self.session = session

    def create_timer(self, data: TimerCreate) -> TimerSession:
        """
        타이머 생성 및 시작
        
        비즈니스 로직:
        - Schedule 존재 확인
        - status를 RUNNING으로 설정
        - started_at을 현재 시간으로 설정
        
        :param data: 타이머 생성 데이터
        :return: 생성된 타이머
        :raises ScheduleNotFoundError: 일정을 찾을 수 없는 경우
        """
        # Schedule 존재 확인
        schedule = schedule_crud.get_schedule(self.session, data.schedule_id)
        if not schedule:
            raise ScheduleNotFoundError()

        # 타이머 생성 (status = RUNNING, started_at = 현재 시간)
        now = ensure_utc_naive(datetime.now(UTC))
        timer_data = {
            "schedule_id": data.schedule_id,
            "title": data.title,
            "description": data.description,
            "allocated_duration": data.allocated_duration,
            "elapsed_time": 0,
            "status": TimerStatus.RUNNING.value,
            "started_at": now,
        }
        return crud.create_timer(self.session, timer_data)

    def get_timer(self, timer_id: UUID) -> TimerSession:
        """
        타이머 조회
        
        비즈니스 로직:
        - 경과 시간을 실시간으로 계산 (status가 RUNNING인 경우)
        
        :param timer_id: 타이머 ID
        :return: 타이머
        :raises TimerNotFoundError: 타이머를 찾을 수 없는 경우
        """
        timer = crud.get_timer(self.session, timer_id)
        if not timer:
            raise TimerNotFoundError()

        # RUNNING 상태인 경우 경과 시간 실시간 계산
        if timer.status == TimerStatus.RUNNING.value and timer.started_at:
            now = ensure_utc_naive(datetime.now(UTC))
            elapsed_since_start = int((now - timer.started_at).total_seconds())
            timer.elapsed_time = max(0, elapsed_since_start)

        return timer

    def get_timers_by_schedule(self, schedule_id: UUID) -> list[TimerSession]:
        """
        일정의 모든 타이머 조회
        
        :param schedule_id: 일정 ID
        :return: 타이머 리스트
        """
        timers = crud.get_timers_by_schedule(self.session, schedule_id)

        # RUNNING 상태인 타이머들의 경과 시간 실시간 계산
        now = ensure_utc_naive(datetime.now(UTC))
        for timer in timers:
            if timer.status == TimerStatus.RUNNING.value and timer.started_at:
                elapsed_since_start = int((now - timer.started_at).total_seconds())
                timer.elapsed_time = max(0, elapsed_since_start)

        return timers

    def get_active_timer(self, schedule_id: UUID) -> TimerSession | None:
        """
        일정의 현재 활성 타이머 조회 (RUNNING 또는 PAUSED)
        
        :param schedule_id: 일정 ID
        :return: 활성 타이머 또는 None
        """
        timer = crud.get_active_timer(self.session, schedule_id)

        if timer and timer.status == TimerStatus.RUNNING.value and timer.started_at:
            # 경과 시간 실시간 계산
            now = ensure_utc_naive(datetime.now(UTC))
            elapsed_since_start = int((now - timer.started_at).total_seconds())
            timer.elapsed_time = max(0, elapsed_since_start)

        return timer

    def pause_timer(self, timer_id: UUID) -> TimerSession:
        """
        타이머 일시정지
        
        비즈니스 로직:
        - status가 RUNNING이어야 함
        - elapsed_time을 현재까지 경과한 시간으로 업데이트
        - status를 PAUSED로 변경
        - paused_at을 현재 시간으로 설정
        
        :param timer_id: 타이머 ID
        :return: 업데이트된 타이머
        :raises TimerNotFoundError: 타이머를 찾을 수 없는 경우
        :raises InvalidTimerStatusError: 잘못된 상태 전이
        """
        timer = crud.get_timer(self.session, timer_id)
        if not timer:
            raise TimerNotFoundError()

        if timer.status != TimerStatus.RUNNING.value:
            raise InvalidTimerStatusError(
                detail=f"Cannot pause timer with status {timer.status}"
            )

        # 경과 시간 계산 및 저장
        now = ensure_utc_naive(datetime.now(UTC))
        if timer.started_at:
            elapsed_since_start = int((now - timer.started_at).total_seconds())
            timer.elapsed_time = max(0, elapsed_since_start)

        # 상태 변경
        timer.status = TimerStatus.PAUSED.value
        timer.paused_at = now

        self.session.flush()
        self.session.refresh(timer)
        return timer

    def resume_timer(self, timer_id: UUID) -> TimerSession:
        """
        타이머 재개
        
        비즈니스 로직:
        - status가 PAUSED이어야 함
        - status를 RUNNING으로 변경
        - started_at을 현재 시간으로 재설정 (경과 시간은 그대로 유지)
        - paused_at을 None으로 설정
        
        :param timer_id: 타이머 ID
        :return: 업데이트된 타이머
        :raises TimerNotFoundError: 타이머를 찾을 수 없는 경우
        :raises InvalidTimerStatusError: 잘못된 상태 전이
        """
        timer = crud.get_timer(self.session, timer_id)
        if not timer:
            raise TimerNotFoundError()

        if timer.status != TimerStatus.PAUSED.value:
            raise InvalidTimerStatusError(
                detail=f"Cannot resume timer with status {timer.status}"
            )

        # 상태 변경
        now = ensure_utc_naive(datetime.now(UTC))
        timer.status = TimerStatus.RUNNING.value
        timer.started_at = now  # 재개 시간으로 재설정
        timer.paused_at = None

        self.session.flush()
        self.session.refresh(timer)
        return timer

    def stop_timer(self, timer_id: UUID) -> TimerSession:
        """
        타이머 종료
        
        비즈니스 로직:
        - status가 RUNNING 또는 PAUSED이어야 함
        - elapsed_time을 최종 경과 시간으로 업데이트
        - status를 COMPLETED로 변경
        - ended_at을 현재 시간으로 설정
        
        :param timer_id: 타이머 ID
        :return: 업데이트된 타이머
        :raises TimerNotFoundError: 타이머를 찾을 수 없는 경우
        :raises InvalidTimerStatusError: 잘못된 상태 전이
        """
        timer = crud.get_timer(self.session, timer_id)
        if not timer:
            raise TimerNotFoundError()

        if timer.status not in [TimerStatus.RUNNING.value, TimerStatus.PAUSED.value]:
            raise InvalidTimerStatusError(
                detail=f"Cannot stop timer with status {timer.status}"
            )

        # 경과 시간 최종 계산
        now = ensure_utc_naive(datetime.now(UTC))
        if timer.status == TimerStatus.RUNNING.value and timer.started_at:
            elapsed_since_start = int((now - timer.started_at).total_seconds())
            timer.elapsed_time = max(0, elapsed_since_start)

        # 상태 변경
        timer.status = TimerStatus.COMPLETED.value
        timer.ended_at = now

        self.session.flush()
        self.session.refresh(timer)
        return timer

    def cancel_timer(self, timer_id: UUID) -> TimerSession:
        """
        타이머 취소
        
        비즈니스 로직:
        - status를 CANCELLED로 변경
        - ended_at을 현재 시간으로 설정
        
        :param timer_id: 타이머 ID
        :return: 업데이트된 타이머
        :raises TimerNotFoundError: 타이머를 찾을 수 없는 경우
        """
        timer = crud.get_timer(self.session, timer_id)
        if not timer:
            raise TimerNotFoundError()

        now = ensure_utc_naive(datetime.now(UTC))
        timer.status = TimerStatus.CANCELLED.value
        timer.ended_at = now

        self.session.flush()
        self.session.refresh(timer)
        return timer

    def update_timer(self, timer_id: UUID, data: TimerUpdate) -> TimerSession:
        """
        타이머 메타데이터 업데이트 (title, description)
        
        :param timer_id: 타이머 ID
        :param data: 업데이트 데이터
        :return: 업데이트된 타이머
        :raises TimerNotFoundError: 타이머를 찾을 수 없는 경우
        """
        timer = crud.get_timer(self.session, timer_id)
        if not timer:
            raise TimerNotFoundError()

        update_data = data.model_dump(exclude_unset=True, exclude_none=True)
        for field, value in update_data.items():
            setattr(timer, field, value)

        self.session.flush()
        self.session.refresh(timer)
        return timer

    def delete_timer(self, timer_id: UUID) -> None:
        """
        타이머 삭제
        
        :param timer_id: 타이머 ID
        :raises TimerNotFoundError: 타이머를 찾을 수 없는 경우
        """
        timer = crud.get_timer(self.session, timer_id)
        if not timer:
            raise TimerNotFoundError()

        crud.delete_timer(self.session, timer)
