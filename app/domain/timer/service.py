"""
Timer Service

FastAPI Best Practices:
- Service는 비즈니스 로직을 담당
- CRUD 함수를 직접 사용 (Repository 패턴 제거)
- Domain Exception을 발생시켜 비즈니스 규칙 위반 표현
- 모든 datetime을 UTC naive로 변환하여 저장
"""
from datetime import datetime, UTC
from typing import Optional, TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from app.domain.schedule.schema.dto import ScheduleRead
    from app.domain.todo.schema.dto import TodoRead

from sqlmodel import Session

from app.core.auth import CurrentUser
from app.core.constants import TimerStatus
from app.crud import timer as crud, schedule as schedule_crud, todo as todo_crud
from app.crud import visibility as visibility_crud
from app.domain.dateutil.service import ensure_utc_naive
from app.domain.schedule.exceptions import ScheduleNotFoundError
from app.domain.tag.service import TagService
from app.domain.timer.exceptions import (
    TimerNotFoundError,
    InvalidTimerStatusError,
)
from app.domain.timer.model import TimerSession
from app.domain.timer.schema.dto import TimerCreate, TimerUpdate
from app.domain.todo.exceptions import TodoNotFoundError
from app.domain.visibility.enums import ResourceType
from app.domain.visibility.service import VisibilityService


class TimerService:
    """
    Timer Service - 비즈니스 로직
    
    FastAPI Best Practices:
    - Repository 패턴 제거, CRUD 함수 직접 사용
    - Session을 받아서 CRUD 함수 호출
    - 모든 datetime을 UTC naive로 변환하여 저장
    - CurrentUser를 받아서 사용자별 데이터 격리
    """

    def __init__(self, session: Session, current_user: CurrentUser):
        self.session = session
        self.current_user = current_user
        self.owner_id = current_user.sub

    def create_timer(self, data: TimerCreate) -> TimerSession:
        """
        타이머 생성 및 시작
        
        비즈니스 로직:
        - schedule_id가 있으면 Schedule 존재 확인
        - todo_id가 있으면 Todo 존재 확인
        - 자동 연결: Todo만 지정 시 연관된 Schedule 자동 연결
        - 자동 연결: Schedule만 지정 시 연관된 source_todo 자동 연결
        - 둘 다 없어도 독립 타이머로 생성 가능
        - status를 RUNNING으로 설정
        - started_at을 현재 시간으로 설정
        
        :param data: 타이머 생성 데이터
        :return: 생성된 타이머
        :raises ScheduleNotFoundError: schedule_id가 있지만 일정을 찾을 수 없는 경우
        :raises TodoNotFoundError: todo_id가 있지만 Todo를 찾을 수 없는 경우
        """
        schedule_id = data.schedule_id
        todo_id = data.todo_id
        
        # Schedule 존재 확인 및 자동 연결 (schedule_id가 있는 경우)
        schedule = None
        if schedule_id:
            schedule = schedule_crud.get_schedule(self.session, schedule_id, self.owner_id)
            if not schedule:
                raise ScheduleNotFoundError()
            
            # Schedule만 지정된 경우 → 연관된 source_todo 자동 연결
            if not todo_id and schedule.source_todo_id:
                todo_id = schedule.source_todo_id

        # Todo 존재 확인 및 자동 연결 (todo_id가 있는 경우)
        todo = None
        if todo_id:
            todo = todo_crud.get_todo(self.session, todo_id, self.owner_id)
            if not todo:
                raise TodoNotFoundError()
            
            # Todo만 지정된 경우 → 연관된 첫 번째 Schedule 자동 연결
            if not schedule_id and todo.schedules:
                schedule_id = todo.schedules[0].id

        # 타이머 생성 (status = RUNNING, started_at = 현재 시간)
        now = ensure_utc_naive(datetime.now(UTC))
        timer_data = {
            "schedule_id": schedule_id,
            "todo_id": todo_id,
            "title": data.title,
            "description": data.description,
            "allocated_duration": data.allocated_duration,
            "elapsed_time": 0,
            "status": TimerStatus.RUNNING.value,
            "started_at": now,
        }
        timer = crud.create_timer(self.session, timer_data, self.owner_id)

        # 가시성 설정
        if data.visibility:
            visibility_service = VisibilityService(self.session, self.current_user)
            visibility_service.set_visibility(
                resource_type=ResourceType.TIMER,
                resource_id=timer.id,
                level=data.visibility.level,
                allowed_user_ids=data.visibility.allowed_user_ids,
            )

        # 태그 설정
        if data.tag_ids:
            tag_service = TagService(self.session, self.current_user)
            tag_service.set_timer_tags(timer.id, data.tag_ids)
            # 태그 설정 후 relationship 갱신
            self.session.refresh(timer)

        return timer

    def get_timer(self, timer_id: UUID) -> TimerSession:
        """
        타이머 조회 (본인 소유만)
        
        비즈니스 로직:
        - 경과 시간을 실시간으로 계산 (status가 RUNNING인 경우)
        
        :param timer_id: 타이머 ID
        :return: 타이머
        :raises TimerNotFoundError: 타이머를 찾을 수 없는 경우
        """
        timer = crud.get_timer(self.session, timer_id, self.owner_id)
        if not timer:
            raise TimerNotFoundError()

        # RUNNING 상태인 경우 경과 시간 실시간 계산
        if timer.status == TimerStatus.RUNNING.value and timer.started_at:
            now = ensure_utc_naive(datetime.now(UTC))
            elapsed_since_start = int((now - timer.started_at).total_seconds())
            timer.elapsed_time = max(0, elapsed_since_start)

        return timer

    def get_timer_with_access_check(self, timer_id: UUID) -> tuple[TimerSession, bool]:
        """
        타이머 조회 (공유 리소스 접근 제어 포함)

        본인 소유이거나 공유 접근 권한이 있는 경우 반환합니다.

        :param timer_id: 타이머 ID
        :return: (타이머, is_shared) 튜플
        :raises TimerNotFoundError: 타이머를 찾을 수 없는 경우
        :raises AccessDeniedError: 접근 권한이 없는 경우
        """

        # 먼저 ID로만 조회 (소유자 무관)
        timer = crud.get_timer_by_id(self.session, timer_id)
        if not timer:
            raise TimerNotFoundError()

        # RUNNING 상태인 경우 경과 시간 실시간 계산
        if timer.status == TimerStatus.RUNNING.value and timer.started_at:
            now = ensure_utc_naive(datetime.now(UTC))
            elapsed_since_start = int((now - timer.started_at).total_seconds())
            timer.elapsed_time = max(0, elapsed_since_start)

        # 본인 소유인 경우
        if timer.owner_id == self.owner_id:
            return timer, False

        # 타인 소유인 경우 접근 권한 확인
        visibility_service = VisibilityService(self.session, self.current_user)
        visibility_service.require_access(
            resource_type=ResourceType.TIMER,
            resource_id=timer_id,
            owner_id=timer.owner_id,
        )

        return timer, True

    def get_shared_timers(self) -> list[TimerSession]:
        """
        공유된 타이머 조회 (타인 소유, 접근 권한 있는 것만)

        N+1 문제 방지를 위해 배치 패턴 사용:
        1. visibility 후보 목록 조회
        2. 리소스 배치 조회
        3. 배치 권한 필터링
        4. RUNNING 상태 경과 시간 계산

        :return: 공유된 타이머 리스트
        """
        # 1. 후보 목록 조회 (visibility != PRIVATE, owner != me)
        visibilities = visibility_crud.get_shared_visibilities(
            self.session,
            ResourceType.TIMER,
            exclude_owner_id=self.owner_id,
        )

        if not visibilities:
            return []

        # 2. 리소스 ID 추출 및 배치 조회
        resource_ids = [v.resource_id for v in visibilities]
        timers = crud.get_timers_by_ids(self.session, resource_ids)

        if not timers:
            return []

        # 3. 배치 권한 필터링
        visibility_service = VisibilityService(self.session, self.current_user)
        accessible_timers = visibility_service.filter_accessible_resources(
            resource_type=ResourceType.TIMER,
            visibilities=visibilities,
            resources=timers,
            get_resource_id=lambda t: t.id,
        )

        # 4. RUNNING 상태인 타이머들의 경과 시간 실시간 계산
        now = ensure_utc_naive(datetime.now(UTC))
        for timer in accessible_timers:
            if timer.status == TimerStatus.RUNNING.value and timer.started_at:
                elapsed_since_start = int((now - timer.started_at).total_seconds())
                timer.elapsed_time = max(0, elapsed_since_start)

        return accessible_timers

    def get_timers_by_schedule(self, schedule_id: UUID) -> list[TimerSession]:
        """
        일정의 모든 타이머 조회
        
        :param schedule_id: 일정 ID
        :return: 타이머 리스트
        """
        timers = crud.get_timers_by_schedule(self.session, schedule_id, self.owner_id)

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
        timer = crud.get_active_timer(self.session, schedule_id, self.owner_id)

        if timer and timer.status == TimerStatus.RUNNING.value and timer.started_at:
            # 경과 시간 실시간 계산
            now = ensure_utc_naive(datetime.now(UTC))
            elapsed_since_start = int((now - timer.started_at).total_seconds())
            timer.elapsed_time = max(0, elapsed_since_start)

        return timer

    def get_timers_by_todo(self, todo_id: UUID) -> list[TimerSession]:
        """
        Todo의 모든 타이머 조회
        
        :param todo_id: Todo ID
        :return: 타이머 리스트
        """
        timers = crud.get_timers_by_todo(self.session, todo_id, self.owner_id)

        # RUNNING 상태인 타이머들의 경과 시간 실시간 계산
        now = ensure_utc_naive(datetime.now(UTC))
        for timer in timers:
            if timer.status == TimerStatus.RUNNING.value and timer.started_at:
                elapsed_since_start = int((now - timer.started_at).total_seconds())
                timer.elapsed_time = max(0, elapsed_since_start)

        return timers

    def get_active_timer_by_todo(self, todo_id: UUID) -> TimerSession | None:
        """
        Todo의 현재 활성 타이머 조회 (RUNNING 또는 PAUSED)
        
        :param todo_id: Todo ID
        :return: 활성 타이머 또는 None
        """
        timer = crud.get_active_timer_by_todo(self.session, todo_id, self.owner_id)

        if timer and timer.status == TimerStatus.RUNNING.value and timer.started_at:
            # 경과 시간 실시간 계산
            now = ensure_utc_naive(datetime.now(UTC))
            elapsed_since_start = int((now - timer.started_at).total_seconds())
            timer.elapsed_time = max(0, elapsed_since_start)

        return timer

    def get_all_timers(
            self,
            status: Optional[list[str]] = None,
            timer_type: Optional[str] = None,
            start_date: Optional[datetime] = None,
            end_date: Optional[datetime] = None,
    ) -> list[TimerSession]:
        """
        사용자의 모든 타이머 조회 (필터링 옵션 지원)

        :param status: 상태 필터 리스트 (RUNNING, PAUSED, COMPLETED, CANCELLED)
        :param timer_type: 타입 필터 (independent, schedule, todo)
        :param start_date: 시작 날짜 필터 (started_at 기준)
        :param end_date: 종료 날짜 필터 (started_at 기준)
        :return: 타이머 리스트
        """
        timers = crud.get_all_timers(
            self.session,
            self.owner_id,
            status=status,
            timer_type=timer_type,
            start_date=start_date,
            end_date=end_date,
        )

        # RUNNING 상태인 타이머들의 경과 시간 실시간 계산
        now = ensure_utc_naive(datetime.now(UTC))
        for timer in timers:
            if timer.status == TimerStatus.RUNNING.value and timer.started_at:
                elapsed_since_start = int((now - timer.started_at).total_seconds())
                timer.elapsed_time = max(0, elapsed_since_start)

        return timers

    def get_user_active_timer(self) -> TimerSession | None:
        """
        사용자의 현재 활성 타이머 조회 (RUNNING 또는 PAUSED)

        여러 개가 있으면 가장 최근 것 반환

        :return: 활성 타이머 또는 None
        """
        timer = crud.get_user_active_timer(self.session, self.owner_id)

        if timer and timer.status == TimerStatus.RUNNING.value and timer.started_at:
            # 경과 시간 실시간 계산
            now = ensure_utc_naive(datetime.now(UTC))
            elapsed_since_start = int((now - timer.started_at).total_seconds())
            timer.elapsed_time = max(0, elapsed_since_start)

        return timer

    def get_all_timers(
            self,
            status: Optional[list[str]] = None,
            timer_type: Optional[str] = None,
            start_date: Optional[datetime] = None,
            end_date: Optional[datetime] = None,
    ) -> list[TimerSession]:
        """
        사용자의 모든 타이머 조회 (필터링 옵션 지원)

        :param status: 상태 필터 리스트 (RUNNING, PAUSED, COMPLETED, CANCELLED)
        :param timer_type: 타입 필터 (independent, schedule, todo)
        :param start_date: 시작 날짜 필터 (started_at 기준)
        :param end_date: 종료 날짜 필터 (started_at 기준)
        :return: 타이머 리스트
        """
        timers = crud.get_all_timers(
            self.session,
            self.owner_id,
            status=status,
            timer_type=timer_type,
            start_date=start_date,
            end_date=end_date,
        )

        # RUNNING 상태인 타이머들의 경과 시간 실시간 계산
        now = ensure_utc_naive(datetime.now(UTC))
        for timer in timers:
            if timer.status == TimerStatus.RUNNING.value and timer.started_at:
                elapsed_since_start = int((now - timer.started_at).total_seconds())
                timer.elapsed_time = max(0, elapsed_since_start)

        return timers

    def get_user_active_timer(self) -> TimerSession | None:
        """
        사용자의 현재 활성 타이머 조회 (RUNNING 또는 PAUSED)

        여러 개가 있으면 가장 최근 것 반환

        :return: 활성 타이머 또는 None
        """
        timer = crud.get_user_active_timer(self.session, self.owner_id)

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
        timer = crud.get_timer(self.session, timer_id, self.owner_id)
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
        timer = crud.get_timer(self.session, timer_id, self.owner_id)
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
        timer = crud.get_timer(self.session, timer_id, self.owner_id)
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
        timer = crud.get_timer(self.session, timer_id, self.owner_id)
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
        타이머 메타데이터 업데이트 (title, description, tags, todo_id, schedule_id)

        todo_id, schedule_id 동작:
        - 필드가 요청에 포함되지 않음: 기존 값 유지
        - 필드가 UUID 값: 해당 ID로 연결 변경 (존재 및 권한 검증)
        - 필드가 null: 연결 해제

        Note: 자동 연결 기능은 적용되지 않음 (명시적 변경만 수행)
        
        :param timer_id: 타이머 ID
        :param data: 업데이트 데이터
        :return: 업데이트된 타이머
        :raises TimerNotFoundError: 타이머를 찾을 수 없는 경우
        :raises TodoNotFoundError: todo_id가 있지만 Todo를 찾을 수 없는 경우
        :raises ScheduleNotFoundError: schedule_id가 있지만 Schedule을 찾을 수 없는 경우
        """
        timer = crud.get_timer(self.session, timer_id, self.owner_id)
        if not timer:
            raise TimerNotFoundError()

        # exclude_unset=True: 요청에 포함되지 않은 필드는 제외
        update_data = data.model_dump(exclude_unset=True)

        # todo_id 처리 (요청에 포함된 경우에만)
        if 'todo_id' in update_data:
            new_todo_id = update_data['todo_id']
            if new_todo_id is not None:
                # 존재 및 권한 검증
                todo = todo_crud.get_todo(self.session, new_todo_id, self.owner_id)
                if not todo:
                    raise TodoNotFoundError()
            timer.todo_id = new_todo_id
            del update_data['todo_id']

        # schedule_id 처리 (요청에 포함된 경우에만)
        if 'schedule_id' in update_data:
            new_schedule_id = update_data['schedule_id']
            if new_schedule_id is not None:
                # 존재 및 권한 검증
                schedule = schedule_crud.get_schedule(self.session, new_schedule_id, self.owner_id)
                if not schedule:
                    raise ScheduleNotFoundError()
            timer.schedule_id = new_schedule_id
            del update_data['schedule_id']

        # 태그 업데이트 (tag_ids가 설정된 경우에만)
        tag_ids_updated = 'tag_ids' in update_data
        if tag_ids_updated:
            tag_service = TagService(self.session, self.current_user)
            tag_service.set_timer_tags(timer.id, update_data['tag_ids'] or [])
            del update_data['tag_ids']  # CRUD에 전달하지 않음

        # 가시성 업데이트 (visibility가 설정된 경우에만)
        if 'visibility' in update_data and update_data['visibility']:
            visibility_data = update_data['visibility']
            visibility_service = VisibilityService(self.session, self.current_user)
            visibility_service.set_visibility(
                resource_type=ResourceType.TIMER,
                resource_id=timer.id,
                level=visibility_data.level,
                allowed_user_ids=visibility_data.allowed_user_ids,
            )
            del update_data['visibility']  # CRUD에 전달하지 않음

        # 나머지 필드 업데이트 (None이 아닌 경우에만)
        for field, value in update_data.items():
            if value is not None:
                setattr(timer, field, value)

        self.session.flush()
        self.session.refresh(timer)

        # 태그가 업데이트된 경우 relationship 갱신
        if tag_ids_updated:
            self.session.refresh(timer)

        return timer

    def delete_timer(self, timer_id: UUID) -> None:
        """
        타이머 삭제
        
        :param timer_id: 타이머 ID
        :raises TimerNotFoundError: 타이머를 찾을 수 없는 경우
        """
        timer = crud.get_timer(self.session, timer_id, self.owner_id)
        if not timer:
            raise TimerNotFoundError()

        # 가시성 설정 삭제
        visibility_crud.delete_visibility_by_resource(
            self.session, ResourceType.TIMER, timer_id
        )

        crud.delete_timer(self.session, timer)

    def to_read_dto(
            self,
            timer: TimerSession,
            is_shared: bool = False,
            schedule: Optional["ScheduleRead"] = None,
            todo: Optional["TodoRead"] = None,
            tag_include_mode: Optional[str] = None,
    ) -> "TimerRead":
        """
        Timer를 TimerRead DTO로 변환하고 가시성 정보를 채웁니다.
        
        [보안 설계] 연관 리소스(Schedule, Todo)는 반드시 외부에서 권한 검증 후 주입받습니다.
        
        이유:
        - 각 도메인 서비스가 독립적으로 권한 검증을 수행하는 Orchestrator 패턴
        - 라우터에서 ScheduleService.get_schedule_with_access_check() 등을 호출하여 권한 검증
        - 권한이 없는 연관 리소스는 null로 전달하여 응답에서 제외
        
        주의: 이 메서드에서 연관 리소스를 직접 조회하면 visibility 검증을 우회하게 됩니다.
              연관 리소스 조회는 반드시 라우터에서 수행하세요.

        :param timer: Timer 모델
        :param is_shared: 공유된 리소스인지 여부
        :param schedule: 외부에서 권한 검증 후 주입된 Schedule DTO (Optional, 권한 없으면 None)
        :param todo: 외부에서 권한 검증 후 주입된 Todo DTO (Optional, 권한 없으면 None)
        :param tag_include_mode: 태그 포함 모드 (none, timer_only, inherit_from_schedule)
        :return: TimerRead DTO (가시성 정보 포함)
        """
        from app.core.constants import TagIncludeMode
        from app.domain.timer.schema.dto import TimerRead

        # 태그 포함 모드 파싱
        if tag_include_mode is None:
            tag_mode = TagIncludeMode.NONE
        elif isinstance(tag_include_mode, str):
            tag_mode = TagIncludeMode(tag_include_mode)
        else:
            tag_mode = tag_include_mode

        # [보안] 연관 리소스는 외부에서 주입받은 것만 사용
        # 내부에서 직접 조회하면 visibility 검증을 우회하게 됨

        # Tags 정보 처리
        tags_read = self._get_timer_tags(timer.id, timer.schedule_id, timer.todo_id, tag_mode)

        # Timer 모델을 TimerRead로 변환
        timer_read = TimerRead.from_model(
            timer,
            include_schedule=(schedule is not None),
            schedule=schedule,
            include_todo=(todo is not None),
            todo=todo,
            tag_include_mode=tag_mode,
            tags=tags_read,
        )

        # 가시성 정보 채우기
        timer_read.owner_id = timer.owner_id
        timer_read.is_shared = is_shared

        # 가시성 레벨 조회
        visibility = visibility_crud.get_visibility_by_resource(
            self.session, ResourceType.TIMER, timer.id
        )
        if visibility:
            timer_read.visibility_level = visibility.level

        return timer_read


    def _get_timer_tags(
            self,
            timer_id: UUID,
            schedule_id: Optional[UUID],
            todo_id: Optional[UUID],
            tag_include_mode,
    ) -> list:
        """
        타이머 태그 조회 헬퍼 메서드
        """
        from app.core.constants import TagIncludeMode
        from app.domain.tag.schema.dto import TagRead

        if tag_include_mode == TagIncludeMode.NONE:
            return []

        tag_service = TagService(self.session, self.current_user)

        if tag_include_mode == TagIncludeMode.TIMER_ONLY:
            tags = tag_service.get_timer_tags(timer_id)
            return [TagRead.model_validate(tag) for tag in tags]

        elif tag_include_mode == TagIncludeMode.INHERIT_FROM_SCHEDULE:
            from app.domain.schedule.service import ScheduleService

            # 타이머 태그 조회
            timer_tags = tag_service.get_timer_tags(timer_id)
            all_tags = {tag.id: tag for tag in timer_tags}

            # 스케줄 태그 조회 (schedule_id가 있는 경우)
            if schedule_id:
                schedule_service = ScheduleService(self.session, self.current_user)
                schedule_tags = schedule_service.get_schedule_tags(schedule_id)
                for tag in schedule_tags:
                    all_tags[tag.id] = tag

            # Todo 태그 조회 (todo_id가 있고 schedule_id가 없는 경우)
            if todo_id and not schedule_id:
                from app.domain.todo.service import TodoService
                todo_service = TodoService(self.session, self.current_user)
                todo_tags = todo_service.get_todo_tags(todo_id)
                for tag in todo_tags:
                    all_tags[tag.id] = tag

            return [TagRead.model_validate(tag) for tag in all_tags.values()]

        return []
