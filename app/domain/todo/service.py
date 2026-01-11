"""
Todo Service

FastAPI Best Practices:
- Service는 비즈니스 로직을 담당
- CRUD 함수를 직접 사용 (Repository 패턴 제거)
- Domain Exception을 발생시켜 비즈니스 규칙 위반 표현
"""
from dataclasses import dataclass
from typing import List, Optional
from uuid import UUID

from sqlmodel import Session, select

from app.crud import schedule as schedule_crud
from app.crud import todo as crud
from app.domain.schedule.schema.dto import ScheduleCreate, ScheduleUpdate
from app.domain.schedule.service import ScheduleService
from app.domain.tag.schema.dto import TagRead
from app.domain.todo.enums import TodoStatus
from app.domain.todo.exceptions import (
    TodoNotFoundError,
    TodoInvalidParentError,
    TodoSelfReferenceError,
    TodoParentGroupMismatchError,
    TodoCycleError,
)
from app.domain.todo.model import Todo
from app.domain.todo.schema.dto import (
    TodoCreate as TodoCreateDTO,
    TodoRead,
    TodoUpdate as TodoUpdateDTO,
    TodoStats,
    TagStat,
    TodoIncludeReason,
)
from app.models.tag import Tag, TodoTag
from app.models.todo import Todo as TodoModel


@dataclass
class TodoListResult:
    """Todo 리스트 조회 결과 (include_reason 포함)"""
    todos: List[Todo]
    include_reason_by_id: dict[UUID, TodoIncludeReason]


class TodoService:
    """
    Todo Service - 비즈니스 로직
    
    Todo는 독립적인 엔티티입니다.
    deadline이 있으면 별도의 Schedule을 생성할 수 있습니다.
    """

    def __init__(self, session: Session):
        self.session = session

    def _validate_parent_id(
            self,
            parent_id: Optional[UUID],
            child_tag_group_id: UUID,
            child_id: Optional[UUID] = None,
    ) -> None:
        """
        parent_id 유효성 검증
        
        검증 규칙:
        - parent_id가 있으면 해당 Todo가 존재해야 함
        - 자기 자신을 부모로 설정 불가
        - 부모와 자식의 tag_group_id가 일치해야 함
        - 순환 참조 생성 불가 (child_id가 parent_id의 조상인 경우)
        
        :param parent_id: 검증할 부모 Todo ID
        :param child_tag_group_id: 자식 Todo의 tag_group_id
        :param child_id: 자식 Todo ID (update 시 자기참조/순환 검증용)
        :raises TodoSelfReferenceError: 자기 자신을 부모로 설정 시
        :raises TodoInvalidParentError: 부모 Todo가 존재하지 않을 때
        :raises TodoParentGroupMismatchError: 그룹이 일치하지 않을 때
        :raises TodoCycleError: 순환 참조가 생성될 때
        """
        if parent_id is None:
            return
        
        # 자기 자신을 부모로 설정 불가
        if child_id is not None and parent_id == child_id:
            raise TodoSelfReferenceError()
        
        # 부모 Todo 존재 확인
        parent = crud.get_todo(self.session, parent_id)
        if not parent:
            raise TodoInvalidParentError()
        
        # 그룹 일관성 확인
        if parent.tag_group_id != child_tag_group_id:
            raise TodoParentGroupMismatchError()
        
        # 순환 참조 검사 (update 시에만 의미 있음)
        # child_id를 parent_id의 조상으로 설정하면 cycle 발생
        if child_id is not None:
            self._check_cycle(parent_id, child_id)
    
    def _check_cycle(self, parent_id: UUID, child_id: UUID) -> None:
        """
        순환 참조 검사
        
        parent_id에서 조상 체인을 따라 올라가며 child_id에 도달하면 cycle.
        무한 루프 방지를 위해 visited set 사용.
        
        :param parent_id: 새로 설정할 부모 ID
        :param child_id: 현재 Todo ID (이 Todo가 parent_id의 조상이면 cycle)
        :raises TodoCycleError: cycle이 감지되면
        """
        visited: set[UUID] = set()
        current_id: Optional[UUID] = parent_id
        
        while current_id is not None:
            # child_id에 도달하면 cycle
            if current_id == child_id:
                raise TodoCycleError()
            
            # 이미 방문한 노드면 기존 데이터에 cycle 있음 - 더 이상 진행 불가
            if current_id in visited:
                break
            
            visited.add(current_id)
            
            # 부모로 이동
            current = crud.get_todo(self.session, current_id)
            if current is None:
                break
            current_id = current.parent_id

    def create_todo(self, data: TodoCreateDTO) -> Todo:
        """
        Todo 생성

        비즈니스 로직:
        - Todo 모델 직접 생성
        - parent_id 지원 (부모 Todo 지정)
        - deadline이 있으면 별도 Schedule 생성 및 source_todo_id 설정
        - 태그는 TagService.set_todo_tags() 사용
        - status 기본값: UNSCHEDULED

        :param data: Todo 생성 데이터
        :return: 생성된 Todo
        :raises TodoInvalidParentError: 부모 Todo가 존재하지 않을 때
        :raises TodoParentGroupMismatchError: 부모와 그룹이 일치하지 않을 때
        """
        # parent_id 검증 (존재/그룹 일치)
        self._validate_parent_id(data.parent_id, data.tag_group_id)
        
        # Todo 모델 생성
        todo = TodoModel(
            title=data.title,
            description=data.description,
            deadline=data.deadline,
            tag_group_id=data.tag_group_id,
            parent_id=data.parent_id,
            status=data.status if data.status is not None else TodoStatus.UNSCHEDULED,
        )
        todo = crud.create_todo(self.session, todo)
        
        # 태그 설정 (Schedule 생성 전에 먼저 설정하여 Schedule에도 태그 복사 가능)
        if data.tag_ids:
            from app.domain.tag.service import TagService
            tag_service = TagService(self.session)
            tag_service.set_todo_tags(todo.id, data.tag_ids)
            self.session.refresh(todo)
        
        # deadline이 있으면 Schedule 생성 (태그도 함께 전달)
        if data.deadline:
            from datetime import timedelta
            # deadline을 start_time으로, end_time은 deadline + 1시간으로 설정
            schedule_data = ScheduleCreate(
                title=data.title,
                description=data.description,
                start_time=data.deadline,
                end_time=data.deadline + timedelta(hours=1),  # deadline + 1시간
                source_todo_id=todo.id,
                tag_ids=data.tag_ids,  # Todo의 태그를 Schedule에도 복사
                # state는 기본값 PLANNED 사용
            )
            schedule_service = ScheduleService(self.session)
            schedule_service.create_schedule(schedule_data)
        
        return todo

    def get_todo(self, todo_id: UUID) -> Todo:
        """
        Todo 조회
        
        :param todo_id: Todo ID
        :return: Todo
        :raises TodoNotFoundError: Todo를 찾을 수 없는 경우
        """
        todo = crud.get_todo(self.session, todo_id)
        if not todo:
            raise TodoNotFoundError()
        return todo

    def get_all_todos(
            self,
            tag_ids: Optional[List[UUID]] = None,
            group_ids: Optional[List[UUID]] = None,
            parent_id: Optional[UUID] = None,
    ) -> TodoListResult:
        """
        모든 Todo 조회 + include_reason 맵 반환
        
        비즈니스 로직:
        - tag_ids: AND 방식 (모든 지정 태그 포함해야 함)
        - group_ids: 해당 그룹에 속한 Todo 반환 (tag_group_id로 직접 연결)
        - parent_id: 부모 Todo로 필터링
        - 정렬: STATUS_ORDER → deadline(오름차순, null은 뒤) → created_at(내림차순)
        - 태그 필터 시 조상도 포함, include_reason으로 MATCH/ANCESTOR 구분
        
        :param tag_ids: 필터링할 태그 ID 리스트 (AND 방식)
        :param group_ids: 필터링할 그룹 ID 리스트
        :param parent_id: 부모 Todo ID (선택)
        :return: TodoListResult (todos + include_reason_by_id)
        """
        # 1. DB 조회 (정렬 적용)
        all_todos = crud.get_todos_sorted(self.session, group_ids, parent_id)
        
        # 2. 태그 필터가 없으면 전부 MATCH
        if not tag_ids:
            reason_map = {t.id: TodoIncludeReason.MATCH for t in all_todos}
            return TodoListResult(todos=all_todos, include_reason_by_id=reason_map)
        
        # 3. 태그 필터 적용 → matched_ids
        matched_ids = self._apply_tag_filter(all_todos, tag_ids)
        
        # 4. parent_by_id 맵 구성 (session.get 최소화)
        parent_by_id = {t.id: t.parent_id for t in all_todos}
        
        # 5. 조상 ID 수집 → ancestor_ids
        ancestor_ids = self._collect_ancestor_ids(parent_by_id, matched_ids)
        
        # 6. include_reason 맵 생성
        reason_map = self._build_include_reason_map(matched_ids, ancestor_ids)
        
        # 7. 정렬 순서 유지하며 visible todos 선택
        visible_ids = matched_ids | ancestor_ids
        visible_todos = [t for t in all_todos if t.id in visible_ids]
        
        return TodoListResult(todos=visible_todos, include_reason_by_id=reason_map)
    
    def _apply_tag_filter(
            self,
            todos: List[Todo],
            tag_ids: List[UUID],
    ) -> set[UUID]:
        """
        태그 필터를 적용하여 매칭된 Todo ID 집합 반환 (AND 방식)
        """
        if not todos or not tag_ids:
            return {t.id for t in todos}
        
        todo_ids = [t.id for t in todos]
        todo_tag_map = crud.get_todo_tag_map(self.session, todo_ids)
        
        tag_ids_set = set(tag_ids)
        return {
            t.id for t in todos
            if tag_ids_set.issubset(todo_tag_map.get(t.id, set()))
        }
    
    def _collect_ancestor_ids(
            self,
            parent_by_id: dict[UUID, Optional[UUID]],
            matched_ids: set[UUID],
    ) -> set[UUID]:
        """
        매칭된 Todo들의 조상 ID 집합 수집 (ANCESTOR 전용, cycle-safe)
        
        parent_by_id 맵을 우선 사용하여 session.get 호출 최소화.
        맵에 없는 조상만 DB에서 조회.
        """
        ancestor_ids: set[UUID] = set()
        visited: set[UUID] = set()
        
        for todo_id in matched_ids:
            current_id: Optional[UUID] = parent_by_id.get(todo_id)
            
            while current_id is not None:
                if current_id in visited:
                    break  # cycle 감지 또는 이미 처리됨
                visited.add(current_id)
                
                if current_id not in matched_ids:
                    ancestor_ids.add(current_id)
                
                # 맵에 있으면 맵에서, 없으면 DB 조회
                if current_id in parent_by_id:
                    current_id = parent_by_id[current_id]
                else:
                    # DB에서 부모 조회 (all_todos에 없는 조상)
                    todo = crud.get_todo(self.session, current_id)
                    if todo is None:
                        break
                    parent_by_id[current_id] = todo.parent_id  # 캐싱
                    current_id = todo.parent_id
        
        return ancestor_ids
    
    @staticmethod
    def _build_include_reason_map(
            matched_ids: set[UUID],
            ancestor_ids: set[UUID],
    ) -> dict[UUID, TodoIncludeReason]:
        """
        matched_ids와 ancestor_ids로부터 include_reason 맵 생성
        """
        reason_map: dict[UUID, TodoIncludeReason] = {}
        for tid in matched_ids:
            reason_map[tid] = TodoIncludeReason.MATCH
        for tid in ancestor_ids:
            reason_map[tid] = TodoIncludeReason.ANCESTOR
        return reason_map

    def update_todo(self, todo_id: UUID, data: TodoUpdateDTO) -> Todo:
        """
        Todo 업데이트
        
        비즈니스 로직:
        - Todo 모델 직접 업데이트
        - deadline 변경 시 Schedule 생성/업데이트/삭제 처리
        - status 업데이트 지원
        - parent_id 업데이트 지원 (트리 구조 변경)
        - 태그는 TagService.set_todo_tags() 사용
        
        :param todo_id: Todo ID
        :param data: 업데이트 데이터
        :return: 업데이트된 Todo
        :raises TodoNotFoundError: Todo를 찾을 수 없는 경우
        :raises TodoSelfReferenceError: 자기 자신을 부모로 설정 시
        :raises TodoInvalidParentError: 부모 Todo가 존재하지 않을 때
        :raises TodoParentGroupMismatchError: 부모와 그룹이 일치하지 않을 때
        """
        todo = self.get_todo(todo_id)
        
        # 업데이트 데이터 준비
        update_dict = data.model_dump(exclude_unset=True)
        
        # parent_id 변경 시 검증
        if 'parent_id' in update_dict:
            new_parent_id = update_dict['parent_id']
            # tag_group_id도 변경될 수 있으므로 새 값 우선 사용
            effective_tag_group_id = update_dict.get('tag_group_id', todo.tag_group_id)
            self._validate_parent_id(new_parent_id, effective_tag_group_id, todo_id)
        
        # deadline 변경 처리
        deadline_updated = 'deadline' in update_dict
        old_deadline = todo.deadline
        new_deadline = update_dict.get('deadline')
        
        if deadline_updated:
            # 기존 Schedule 조회
            existing_schedules = schedule_crud.get_schedules_by_source_todo_id(self.session, todo_id)
            
            if old_deadline and not new_deadline:
                # deadline 제거: 기존 Schedule 삭제
                schedule_service = ScheduleService(self.session)
                for schedule in existing_schedules:
                    schedule_service.delete_schedule(schedule.id)
            elif not old_deadline and new_deadline:
                # deadline 추가: 새 Schedule 생성
                from datetime import timedelta
                # Todo의 기존 태그 가져오기
                todo_tags = self.get_todo_tags(todo.id)
                tag_ids = [tag.id for tag in todo_tags] if todo_tags else None
                schedule_data = ScheduleCreate(
                    title=todo.title,
                    description=todo.description,
                    start_time=new_deadline,
                    end_time=new_deadline + timedelta(hours=1),  # deadline + 1시간
                    source_todo_id=todo.id,
                    tag_ids=tag_ids,  # Todo의 태그를 Schedule에도 복사
                    # state는 기본값 PLANNED 사용
                )
                schedule_service = ScheduleService(self.session)
                schedule_service.create_schedule(schedule_data)
            elif old_deadline and new_deadline:
                # deadline 변경: 기존 Schedule 업데이트
                if existing_schedules:
                    from datetime import timedelta
                    schedule_service = ScheduleService(self.session)
                    # Todo의 기존 태그 가져오기
                    todo_tags = self.get_todo_tags(todo.id)
                    tag_ids = [tag.id for tag in todo_tags] if todo_tags else None
                    schedule_update = ScheduleUpdate(
                        start_time=new_deadline,
                        end_time=new_deadline + timedelta(hours=1),  # deadline + 1시간
                        tag_ids=tag_ids,  # Todo의 태그를 Schedule에도 동기화
                    )
                    schedule_service.update_schedule(existing_schedules[0].id, schedule_update)
        
        # 태그 업데이트 (tag_ids가 설정된 경우에만)
        tag_ids_updated = 'tag_ids' in update_dict
        if tag_ids_updated:
            from app.domain.tag.service import TagService
            tag_service = TagService(self.session)
            tag_service.set_todo_tags(todo.id, update_dict['tag_ids'] or [])
            # Todo의 Schedule이 있으면 태그도 동기화
            schedules = schedule_crud.get_schedules_by_source_todo_id(self.session, todo_id)
            if schedules:
                schedule_service = ScheduleService(self.session)
                for schedule in schedules:
                    schedule_update = ScheduleUpdate(tag_ids=update_dict['tag_ids'] or [])
                    schedule_service.update_schedule(schedule.id, schedule_update)
            del update_dict['tag_ids']
        
        # 나머지 필드 업데이트
        for key, value in update_dict.items():
            setattr(todo, key, value)
        
        self.session.flush()
        self.session.refresh(todo)
        
        return todo

    def delete_todo(self, todo_id: UUID) -> None:
        """
        Todo 삭제
        
        비즈니스 로직:
        - 외부 캘린더 sync 고려: 서비스 로직에서 명시적으로 연관된 Schedule 삭제
        - source_todo_id로 연관된 모든 Schedule 조회
        - 각 Schedule에 대해 ScheduleService.delete_schedule() 명시적 호출
        - 그 후 Todo 삭제
        - 자식 Todo 처리 (함께 삭제 - cascade)
        
        :param todo_id: Todo ID
        :raises TodoNotFoundError: Todo를 찾을 수 없는 경우
        """
        todo = self.get_todo(todo_id)
        
        # 연관된 Schedule 명시적 삭제 (외부 캘린더 sync 고려)
        schedules = schedule_crud.get_schedules_by_source_todo_id(self.session, todo_id)
        
        schedule_service = ScheduleService(self.session)
        for schedule in schedules:
            schedule_service.delete_schedule(schedule.id)
        
        # 자식 Todo도 함께 삭제 (cascade)
        # DB 레벨 cascade로 처리되지만, 명시적으로 확인
        children = crud.get_children_by_parent_id(self.session, todo_id)
        for child in children:
            self.delete_todo(child.id)  # 재귀적 삭제
        
        # Todo 삭제
        crud.delete_todo(self.session, todo)

    def get_todo_tags(self, todo_id: UUID) -> List[Tag]:
        """
        Todo의 태그 조회
        
        :param todo_id: Todo ID
        :return: 태그 리스트
        """
        from app.domain.tag.service import TagService
        tag_service = TagService(self.session)
        return tag_service.get_todo_tags(todo_id)

    def get_todo_stats(self, group_id: Optional[UUID] = None) -> TodoStats:
        """
        Todo 통계 조회
        
        :param group_id: 필터링할 그룹 ID (선택)
        :return: Todo 통계
        """
        # Todo 조회
        result = self.get_all_todos(group_ids=[group_id] if group_id else None)
        todos = result.todos
        
        # Todo별 태그 조회
        todo_ids = [t.id for t in todos]
        if not todo_ids:
            return TodoStats(
                group_id=group_id,
                total_count=0,
                by_tag=[],
            )
        
        # 태그별 카운트 집계
        statement = (
            select(TodoTag.tag_id, Tag.name)
            .join(Tag)
            .where(TodoTag.todo_id.in_(todo_ids))
        )
        
        # 그룹 필터링
        if group_id:
            statement = statement.where(Tag.group_id == group_id)
        
        tag_rows = self.session.exec(statement).all()
        
        # 태그별 카운트
        tag_counts: dict[UUID, dict] = {}
        for tag_id, tag_name in tag_rows:
            if tag_id not in tag_counts:
                tag_counts[tag_id] = {"name": tag_name, "count": 0}
            tag_counts[tag_id]["count"] += 1
        
        by_tag = [
            TagStat(tag_id=tag_id, tag_name=info["name"], count=info["count"])
            for tag_id, info in tag_counts.items()
        ]
        
        return TodoStats(
            group_id=group_id,
            total_count=len(todos),
            by_tag=by_tag,
        )

    def to_read_dto(
            self,
            todo: Todo,
            include_reason: TodoIncludeReason = TodoIncludeReason.MATCH,
    ) -> TodoRead:
        """
        Todo를 TodoRead DTO로 변환
        
        :param todo: Todo 모델
        :param include_reason: 포함 사유 (MATCH/ANCESTOR)
        :return: TodoRead DTO
        """
        from app.domain.schedule.schema.dto import ScheduleRead
        
        tags = self.get_todo_tags(todo.id)
        tag_reads = [TagRead.model_validate(tag) for tag in tags]
        
        # 연관된 Schedule 조회
        schedules = schedule_crud.get_schedules_by_source_todo_id(self.session, todo.id)
        schedule_reads = [ScheduleRead.model_validate(s) for s in schedules]
        
        return TodoRead(
            id=todo.id,
            title=todo.title,
            description=todo.description,
            deadline=todo.deadline,
            tag_group_id=todo.tag_group_id,
            parent_id=todo.parent_id,
            status=todo.status,
            created_at=todo.created_at,
            tags=tag_reads,
            schedules=schedule_reads,
            include_reason=include_reason,
        )
