"""
Todo Router

FastAPI Best Practices:
- 모든 라우트는 async
- Service는 session을 받아서 CRUD 직접 사용
- Todo 전용 엔드포인트 (Schedule과 분리)

[보안 설계 - Clean Architecture Orchestrator 패턴]
- Router가 orchestrator 역할을 수행
- 각 도메인 서비스는 자신의 리소스만 처리 (서비스 간 직접 호출 금지)
- 연관 리소스는 라우터에서 각 서비스를 독립적으로 호출하여 조합
  - ScheduleService.try_get_schedule_read(): Schedule 권한 검증 후 DTO 반환
  - TodoService.to_read_dto(): 검증된 DTO를 주입받아 최종 DTO 생성
"""
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session

from app.core.auth import CurrentUser, get_current_user
from app.core.constants import ResourceScope
from app.crud import schedule as schedule_crud
from app.db.session import get_db_transactional
from app.domain.dateutil.service import parse_timezone
from app.domain.schedule.service import ScheduleService
from app.domain.schedule.schema.dto import ScheduleRead
from app.domain.timer.schema.dto import TimerRead
from app.domain.timer.service import TimerService
from app.domain.todo.schema.dto import (
    TodoCreate,
    TodoRead,
    TodoUpdate,
    TodoStats,
    TodoIncludeReason,
)
from app.domain.todo.service import TodoService

router = APIRouter(prefix="/todos", tags=["Todos"])


def _get_related_schedule_reads(
        todo,
        schedule_service: ScheduleService,
        is_shared: bool = False,
) -> List[ScheduleRead]:
    """
    Todo의 연관 Schedule을 권한 검증 후 조회 (라우터 orchestrator 헬퍼)
    
    [Clean Architecture] 라우터가 ScheduleService를 직접 호출합니다.
    - 서비스 간 직접 호출 없음
    - 각 Schedule에 대해 ScheduleService.try_get_schedule_read() 호출
    
    :param todo: Todo 모델
    :param schedule_service: ScheduleService 인스턴스
    :param is_shared: 공유된 Todo인지 여부
    :return: 접근 가능한 Schedule DTO 리스트
    """
    schedule_owner_id = todo.owner_id if is_shared else schedule_service.owner_id
    schedules = schedule_crud.get_schedules_by_source_todo_id(
        schedule_service.session, todo.id, schedule_owner_id
    )
    
    schedule_reads = []
    for schedule in schedules:
        schedule_read = schedule_service.try_get_schedule_read(schedule.id)
        if schedule_read:
            schedule_reads.append(schedule_read)
    
    return schedule_reads


@router.post("", response_model=TodoRead, status_code=status.HTTP_201_CREATED)
async def create_todo(
        data: TodoCreate,
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    새 Todo 생성
    
    Todo는 독립적인 엔티티입니다.
    deadline이 있으면 별도의 Schedule이 자동으로 생성됩니다.
    """
    todo_service = TodoService(session, current_user)
    schedule_service = ScheduleService(session, current_user)
    
    todo = todo_service.create_todo(data)
    
    # 연관 Schedule 조회 및 DTO 생성 (라우터에서 orchestration)
    schedule_reads = _get_related_schedule_reads(todo, schedule_service, is_shared=False)
    return todo_service.to_read_dto(todo, schedules=schedule_reads)


@router.get("", response_model=list[TodoRead])
async def read_todos(
        scope: ResourceScope = Query(
            ResourceScope.MINE,
            description="조회 범위: mine(내 Todo만), shared(공유된 Todo만), all(모두)"
        ),
        tag_ids: Optional[List[UUID]] = Query(
            None,
            description="태그 ID 리스트 (AND 방식: 모든 지정 태그를 포함한 Todo만 반환)"
        ),
        group_ids: Optional[List[UUID]] = Query(
            None,
            description="태그 그룹 ID 리스트 (해당 그룹에 속한 Todo 반환 - 직접 연결 또는 태그 기반)"
        ),
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    Todo 목록 조회 (태그/그룹 필터링 지원)
    
    조회 범위 (scope):
    - mine: 내 Todo만 (기본값)
    - shared: 공유된 타인의 Todo만
    - all: 내 Todo + 공유된 Todo
    
    그룹 필터링:
    - group_ids: 해당 그룹에 속한 Todo 반환
      - tag_group_id로 직접 연결된 Todo
      - OR 해당 그룹의 태그를 가진 Todo
    
    태그 필터링:
    - tag_ids: AND 방식 (모든 지정 태그를 포함한 Todo만 반환)
    - 태그 필터 시 조상 노드도 포함 (orphan 방지)
    
    응답의 include_reason 필드:
    - MATCH: 필터 조건에 직접 매칭된 Todo
    - ANCESTOR: 매칭된 Todo의 조상이라 포함된 Todo
    
    둘 다 지정 시: 그룹 필터링 후 태그 필터링 적용
    """
    todo_service = TodoService(session, current_user)
    schedule_service = ScheduleService(session, current_user)
    result_list = []

    # 내 Todo 조회 (scope=mine 또는 scope=all)
    if scope in (ResourceScope.MINE, ResourceScope.ALL):
        result = todo_service.get_all_todos(tag_ids=tag_ids, group_ids=group_ids)
        for todo in result.todos:
            # 연관 Schedule 조회 (라우터에서 orchestration)
            schedule_reads = _get_related_schedule_reads(todo, schedule_service, is_shared=False)
            todo_read = todo_service.to_read_dto(
                todo,
                include_reason=result.include_reason_by_id.get(todo.id, TodoIncludeReason.MATCH),
                is_shared=False,
                schedules=schedule_reads,
            )
            result_list.append(todo_read)

    # 공유된 Todo 조회 (scope=shared 또는 scope=all)
    if scope in (ResourceScope.SHARED, ResourceScope.ALL):
        shared_todos = todo_service.get_shared_todos()
        for todo in shared_todos:
            # group_ids 필터 적용 (shared에도)
            if group_ids and todo.tag_group_id not in group_ids:
                continue

            # tag_ids 필터 적용 (AND 방식)
            if tag_ids:
                todo_tag_ids = {tag.id for tag in todo.tags}
                if not all(tid in todo_tag_ids for tid in tag_ids):
                    continue

            # 연관 Schedule 조회 (라우터에서 orchestration)
            schedule_reads = _get_related_schedule_reads(todo, schedule_service, is_shared=True)
            todo_read = todo_service.to_read_dto(todo, is_shared=True, schedules=schedule_reads)
            result_list.append(todo_read)

    return result_list


@router.get("/stats", response_model=TodoStats)
async def get_todo_stats(
        group_id: Optional[UUID] = Query(
            None,
            description="필터링할 태그 그룹 ID"
        ),
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    Todo 통계 조회
    
    그룹별 태그 통계를 반환합니다.
    group_id가 지정되면 해당 그룹의 태그만 집계합니다.
    """
    todo_service = TodoService(session, current_user)
    return todo_service.get_todo_stats(group_id=group_id)


@router.get("/{todo_id}", response_model=TodoRead)
async def read_todo(
        todo_id: UUID,
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    ID로 Todo 조회 (공유된 Todo 포함)
    
    본인 소유 Todo 또는 공유 접근 권한이 있는 Todo를 조회합니다.
    접근 권한이 없으면 403 Forbidden을 반환합니다.
    """
    todo_service = TodoService(session, current_user)
    schedule_service = ScheduleService(session, current_user)
    
    todo, is_shared = todo_service.get_todo_with_access_check(todo_id)
    
    # 연관 Schedule 조회 및 DTO 생성 (라우터에서 orchestration)
    schedule_reads = _get_related_schedule_reads(todo, schedule_service, is_shared=is_shared)
    return todo_service.to_read_dto(todo, is_shared=is_shared, schedules=schedule_reads)


@router.patch("/{todo_id}", response_model=TodoRead)
async def update_todo(
        todo_id: UUID,
        data: TodoUpdate,
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    Todo 업데이트
    
    title, description, tag_ids, deadline, parent_id, status를 업데이트할 수 있습니다.
    
    deadline 변경 시:
    - deadline 추가: 새 Schedule 생성
    - deadline 변경: 기존 Schedule 업데이트
    - deadline 제거: 기존 Schedule 삭제
    """
    todo_service = TodoService(session, current_user)
    schedule_service = ScheduleService(session, current_user)
    
    todo = todo_service.update_todo(todo_id, data)
    
    # 연관 Schedule 조회 및 DTO 생성 (라우터에서 orchestration)
    schedule_reads = _get_related_schedule_reads(todo, schedule_service, is_shared=False)
    return todo_service.to_read_dto(todo, schedules=schedule_reads)


@router.delete("/{todo_id}", status_code=status.HTTP_200_OK)
async def delete_todo(
        todo_id: UUID,
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    Todo 삭제
    """
    todo_service = TodoService(session, current_user)
    todo_service.delete_todo(todo_id)
    return {"ok": True}


@router.get("/{todo_id}/timers", response_model=list[TimerRead])
async def get_todo_timers(
        todo_id: UUID,
        include_todo: bool = Query(
            False,
            description="Todo 정보 포함 여부 (기본값: false)"
        ),
        tz: Optional[str] = Query(
            None,
            alias="timezone",
            description="타임존 (예: UTC, +09:00, Asia/Seoul). 지정하지 않으면 UTC로 반환"
        ),
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    Todo의 모든 타이머 조회 (공유된 Todo 포함)
    
    Schedule의 /schedules/{schedule_id}/timers 엔드포인트와 동일한 패턴입니다.
    """
    todo_service = TodoService(session, current_user)
    schedule_service = ScheduleService(session, current_user)
    
    todo, is_shared = todo_service.get_todo_with_access_check(todo_id)

    timer_service = TimerService(session, current_user)
    timers = timer_service.get_timers_by_todo(todo.id)

    # Todo 정보 처리 (라우터에서 orchestration)
    todo_read = None
    if include_todo:
        schedule_reads = _get_related_schedule_reads(todo, schedule_service, is_shared=is_shared)
        todo_read = todo_service.to_read_dto(todo, is_shared=is_shared, schedules=schedule_reads)

    tz_obj = parse_timezone(tz) if tz else None
    return [
        TimerRead.from_model(
            timer,
            include_todo=include_todo,
            todo=todo_read,
        ).to_timezone(tz_obj, validate=False)
        for timer in timers
    ]


@router.get("/{todo_id}/timers/active", response_model=TimerRead)
async def get_todo_active_timer(
        todo_id: UUID,
        include_todo: bool = Query(
            False,
            description="Todo 정보 포함 여부 (기본값: false)"
        ),
        tz: Optional[str] = Query(
            None,
            alias="timezone",
            description="타임존 (예: UTC, +09:00, Asia/Seoul). 지정하지 않으면 UTC로 반환"
        ),
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    Todo의 현재 활성 타이머 조회 (RUNNING 또는 PAUSED, 공유된 Todo 포함)
    
    활성 타이머가 없으면 404를 반환합니다.
    Schedule의 /schedules/{schedule_id}/timers/active 엔드포인트와 동일한 패턴입니다.
    """
    from app.domain.timer.exceptions import TimerNotFoundError

    todo_service = TodoService(session, current_user)
    schedule_service = ScheduleService(session, current_user)
    
    todo, is_shared = todo_service.get_todo_with_access_check(todo_id)

    timer_service = TimerService(session, current_user)
    timer = timer_service.get_active_timer_by_todo(todo.id)
    if not timer:
        raise TimerNotFoundError()

    # Todo 정보 처리 (라우터에서 orchestration)
    todo_read = None
    if include_todo:
        schedule_reads = _get_related_schedule_reads(todo, schedule_service, is_shared=is_shared)
        todo_read = todo_service.to_read_dto(todo, is_shared=is_shared, schedules=schedule_reads)

    # Timer 모델을 TimerRead로 변환 (안전한 변환 - 관계 필드 제외)
    timer_read = TimerRead.from_model(
        timer,
        include_todo=include_todo,
        todo=todo_read,
    )

    # 타임존 변환 (from_model로 이미 검증된 인스턴스이므로 validate=False)
    tz_obj = parse_timezone(tz) if tz else None
    return timer_read.to_timezone(tz_obj, validate=False)
