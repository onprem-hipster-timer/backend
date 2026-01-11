"""
Todo Service

FastAPI Best Practices:
- Service는 비즈니스 로직을 담당
- CRUD 함수를 직접 사용 (Repository 패턴 제거)
- Domain Exception을 발생시켜 비즈니스 규칙 위반 표현
"""
from typing import List, Optional
from uuid import UUID

from sqlalchemy import case
from sqlmodel import Session, select

from app.domain.schedule.schema.dto import ScheduleCreate
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
from app.domain.todo.schema.dto import TodoCreate, TodoRead, TodoUpdate, TodoStats, TagStat
from app.models.tag import Tag, TodoTag
from app.models.todo import Todo as TodoModel

# 정렬 우선순위용 상태 순서
STATUS_ORDER: dict[TodoStatus, int] = {
    TodoStatus.UNSCHEDULED: 0,
    TodoStatus.SCHEDULED: 1,
    TodoStatus.DONE: 2,
    TodoStatus.CANCELLED: 3,
}


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
        parent = self.session.get(TodoModel, parent_id)
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
            current = self.session.get(TodoModel, current_id)
            if current is None:
                break
            current_id = current.parent_id

    def create_todo(self, data: TodoCreate) -> Todo:
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
        self.session.add(todo)
        self.session.flush()
        self.session.refresh(todo)
        
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
        todo = self.session.get(TodoModel, todo_id)
        if not todo:
            raise TodoNotFoundError()
        return todo

    def get_all_todos(
            self,
            tag_ids: Optional[List[UUID]] = None,
            group_ids: Optional[List[UUID]] = None,
            parent_id: Optional[UUID] = None,
    ) -> List[Todo]:
        """
        모든 Todo 조회 (태그/그룹 필터링 지원)
        
        비즈니스 로직:
        - tag_ids: AND 방식 (모든 지정 태그 포함해야 함)
        - group_ids: 해당 그룹에 속한 Todo 반환 (tag_group_id로 직접 연결)
        - parent_id: 부모 Todo로 필터링
        - 정렬: STATUS_ORDER → deadline(오름차순, null은 뒤) → created_at(내림차순)
        
        :param tag_ids: 필터링할 태그 ID 리스트 (AND 방식)
        :param group_ids: 필터링할 그룹 ID 리스트
        :param parent_id: 부모 Todo ID (선택)
        :return: Todo 리스트
        """
        # 상태 우선순위 정렬을 위한 CASE 표현식
        status_order_expr = case(
            {status.value: order for status, order in STATUS_ORDER.items()},
            value=TodoModel.status,
            else_=999,
        )
        
        # deadline null last 처리: null이면 1, 아니면 0
        deadline_null_expr = case(
            (TodoModel.deadline.is_(None), 1),
            else_=0,
        )
        
        statement = (
            select(TodoModel)
            .order_by(
                status_order_expr,           # 1. STATUS_ORDER 오름차순
                deadline_null_expr,          # 2-1. deadline null은 뒤로
                TodoModel.deadline.asc(),    # 2-2. deadline 오름차순
                TodoModel.created_at.desc(), # 3. created_at 내림차순
            )
        )
        
        # 그룹 필터링
        if group_ids:
            statement = statement.where(TodoModel.tag_group_id.in_(group_ids))
        
        # 부모 필터링
        if parent_id is not None:
            statement = statement.where(TodoModel.parent_id == parent_id)
        
        todos = list(self.session.exec(statement).all())
        
        # 태그 필터링 (태그가 지정된 경우)
        if tag_ids:
            filtered = self._filter_todos_by_tags(todos, tag_ids)
            # 필터링된 Todo들의 조상도 함께 포함 (orphan 방지)
            todos = self._include_ancestors(todos, filtered)
        
        return todos
    
    def _get_ancestor_ids(self, todo_id: UUID, visited: set[UUID]) -> List[UUID]:
        """
        주어진 Todo의 모든 조상 ID를 반환 (cycle 안전)
        
        :param todo_id: 조상을 찾을 Todo ID
        :param visited: 이미 방문한 ID들 (무한 루프 방지)
        :return: 조상 ID 리스트 (루트에서 가까운 순)
        """
        ancestors: List[UUID] = []
        current_id: Optional[UUID] = todo_id
        
        while current_id is not None:
            if current_id in visited:
                break
            visited.add(current_id)
            
            current = self.session.get(TodoModel, current_id)
            if current is None or current.parent_id is None:
                break
            
            ancestors.append(current.parent_id)
            current_id = current.parent_id
        
        return ancestors
    
    def _include_ancestors(
            self,
            all_todos: List[Todo],
            filtered_todos: List[Todo],
    ) -> List[Todo]:
        """
        필터링된 Todo 리스트에 조상 노드들을 포함시킴
        
        :param all_todos: 전체 Todo 리스트 (정렬된 상태)
        :param filtered_todos: 필터로 매칭된 Todo 리스트
        :return: 조상이 포함된 Todo 리스트 (정렬 유지)
        """
        # 필터된 Todo ID 집합
        filtered_ids = {t.id for t in filtered_todos}
        
        # 조상 ID 수집
        ancestor_ids: set[UUID] = set()
        visited: set[UUID] = set()
        
        for todo in filtered_todos:
            ancestors = self._get_ancestor_ids(todo.id, visited.copy())
            ancestor_ids.update(ancestors)
        
        # 이미 필터에 포함된 것은 제외
        ancestor_ids -= filtered_ids
        
        # 조상이 없으면 필터된 결과 그대로 반환
        if not ancestor_ids:
            return filtered_todos
        
        # 전체 리스트에서 조상과 필터된 항목을 정렬 순서 유지하며 반환
        result_ids = filtered_ids | ancestor_ids
        return [t for t in all_todos if t.id in result_ids]

    def _filter_todos_by_tags(
            self,
            todos: List[Todo],
            tag_ids: Optional[List[UUID]] = None,
    ) -> List[Todo]:
        """
        Todo를 태그로 필터링
        
        :param todos: 필터링할 Todo 리스트
        :param tag_ids: 필터링할 태그 ID 리스트 (AND 방식)
        :return: 필터링된 Todo 리스트
        """
        if not todos or not tag_ids:
            return todos
        
        # Todo별 태그 조회 (N+1 방지)
        todo_ids = [t.id for t in todos]
        statement = (
            select(TodoTag.todo_id, TodoTag.tag_id)
            .where(TodoTag.todo_id.in_(todo_ids))
        )
        todo_tag_rows = self.session.exec(statement).all()
        
        # Todo별 태그 매핑
        todo_tag_map: dict[UUID, set[UUID]] = {}
        for todo_id, tag_id in todo_tag_rows:
            if todo_id not in todo_tag_map:
                todo_tag_map[todo_id] = set()
            todo_tag_map[todo_id].add(tag_id)
        
        # 태그 필터링 (AND 방식)
        filtered_todos = []
        tag_ids_set = set(tag_ids)
        for todo in todos:
            todo_tags = todo_tag_map.get(todo.id, set())
            if tag_ids_set.issubset(todo_tags):
                filtered_todos.append(todo)
        
        return filtered_todos

    def update_todo(self, todo_id: UUID, data: TodoUpdate) -> Todo:
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
            from app.crud.schedule import get_schedules_by_source_todo_id
            existing_schedules = get_schedules_by_source_todo_id(self.session, todo_id)
            
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
                    from app.domain.schedule.schema.dto import ScheduleUpdate
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
            from app.crud.schedule import get_schedules_by_source_todo_id
            schedules = get_schedules_by_source_todo_id(self.session, todo_id)
            if schedules:
                schedule_service = ScheduleService(self.session)
                from app.domain.schedule.schema.dto import ScheduleUpdate
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
        from app.crud.schedule import get_schedules_by_source_todo_id
        schedules = get_schedules_by_source_todo_id(self.session, todo_id)
        
        schedule_service = ScheduleService(self.session)
        for schedule in schedules:
            schedule_service.delete_schedule(schedule.id)
        
        # 자식 Todo도 함께 삭제 (cascade)
        # DB 레벨 cascade로 처리되지만, 명시적으로 확인
        children = self.session.exec(
            select(TodoModel).where(TodoModel.parent_id == todo_id)
        ).all()
        for child in children:
            self.delete_todo(child.id)  # 재귀적 삭제
        
        # Todo 삭제
        self.session.delete(todo)
        # commit은 get_db_transactional이 처리

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
        todos = self.get_all_todos(group_ids=[group_id] if group_id else None)
        
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

    def to_read_dto(self, todo: Todo) -> TodoRead:
        """
        Todo를 TodoRead DTO로 변환
        
        :param todo: Todo 모델
        :return: TodoRead DTO
        """
        tags = self.get_todo_tags(todo.id)
        tag_reads = [TagRead.model_validate(tag) for tag in tags]
        
        # 연관된 Schedule 조회
        from app.crud.schedule import get_schedules_by_source_todo_id
        from app.domain.schedule.schema.dto import ScheduleRead
        schedules = get_schedules_by_source_todo_id(self.session, todo.id)
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
        )
