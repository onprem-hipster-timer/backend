"""
Todo Service

FastAPI Best Practices:
- Service는 비즈니스 로직을 담당
- CRUD 함수를 직접 사용 (Repository 패턴 제거)
- Domain Exception을 발생시켜 비즈니스 규칙 위반 표현
"""
from typing import List, Optional
from uuid import UUID

from sqlmodel import Session, select

from app.crud import schedule as schedule_crud
from app.domain.schedule.schema.dto import ScheduleCreate
from app.domain.tag.schema.dto import TagRead
from app.domain.todo.constants import TODO_DATETIME, TODO_DATETIME_END
from app.domain.todo.exceptions import TodoNotFoundError, NotATodoError, DeadlineRequiredForConversionError
from app.domain.todo.model import Todo
from app.domain.todo.schema.dto import TodoCreate, TodoRead, TodoUpdate, TodoStats, TagStat
from app.models.tag import Tag, ScheduleTag


class TodoService:
    """
    Todo Service - 비즈니스 로직
    
    Todo는 is_todo=True인 Schedule입니다.
    마감 시간이 있으면 일정 목록에도 표시되고,
    없으면 start_time=917초로 설정됩니다.
    """

    def __init__(self, session: Session):
        self.session = session

    def _is_todo(self, schedule: Todo) -> bool:
        """Schedule이 Todo인지 확인 (is_todo 필드 사용)"""
        return schedule.is_todo

    def create_todo(self, data: TodoCreate) -> Todo:
        """
        Todo 생성
        
        비즈니스 로직:
        - is_todo=True로 설정
        - start_time/end_time이 제공되지 않으면 TODO_DATETIME (917초)으로 설정
        - 태그 설정 (tag_ids가 있는 경우)
        
        :param data: Todo 생성 데이터
        :return: 생성된 Todo
        """
        # 마감 시간이 없으면 TODO_DATETIME 사용
        start_time = data.start_time if data.start_time else TODO_DATETIME
        end_time = data.end_time if data.end_time else TODO_DATETIME_END
        
        # ScheduleCreate로 변환
        schedule_data = ScheduleCreate(
            title=data.title,
            description=data.description,
            start_time=start_time,
            end_time=end_time,
            tag_ids=data.tag_ids,
            is_todo=True,  # Todo 플래그 설정
        )
        
        # Schedule 생성 CRUD 직접 사용
        todo = schedule_crud.create_schedule(self.session, schedule_data)
        
        # 태그 설정
        if data.tag_ids:
            from app.domain.tag.service import TagService
            tag_service = TagService(self.session)
            tag_service.set_schedule_tags(todo.id, data.tag_ids)
            self.session.refresh(todo)
        
        return todo

    def get_todo(self, todo_id: UUID) -> Todo:
        """
        Todo 조회
        
        :param todo_id: Todo ID
        :return: Todo
        :raises TodoNotFoundError: Todo를 찾을 수 없는 경우
        :raises NotATodoError: 일정이 Todo가 아닌 경우
        """
        todo = schedule_crud.get_schedule(self.session, todo_id)
        if not todo:
            raise TodoNotFoundError()
        
        if not self._is_todo(todo):
            raise NotATodoError()
        
        return todo

    def get_all_todos(
            self,
            tag_ids: Optional[List[UUID]] = None,
            group_ids: Optional[List[UUID]] = None,
    ) -> List[Todo]:
        """
        모든 Todo 조회 (태그 필터링 지원)
        
        비즈니스 로직:
        - is_todo=True인 일정만 조회
        - tag_ids: AND 방식 (모든 지정 태그 포함해야 함)
        - group_ids: 해당 그룹의 태그 중 하나라도 있으면 포함
        
        :param tag_ids: 필터링할 태그 ID 리스트 (AND 방식)
        :param group_ids: 필터링할 그룹 ID 리스트
        :return: Todo 리스트
        """
        # Todo만 조회 (is_todo=True인 일정)
        statement = (
            select(Todo)
            .where(Todo.is_todo == True)
            .order_by(Todo.created_at.desc())
        )
        todos = list(self.session.exec(statement).all())
        
        # 태그 필터링
        if tag_ids or group_ids:
            todos = self._filter_todos_by_tags(todos, tag_ids, group_ids)
        
        return todos

    def _filter_todos_by_tags(
            self,
            todos: List[Todo],
            tag_ids: Optional[List[UUID]] = None,
            group_ids: Optional[List[UUID]] = None,
    ) -> List[Todo]:
        """
        Todo를 태그로 필터링
        
        :param todos: 필터링할 Todo 리스트
        :param tag_ids: 필터링할 태그 ID 리스트 (AND 방식)
        :param group_ids: 필터링할 그룹 ID 리스트
        :return: 필터링된 Todo 리스트
        """
        if not todos:
            return todos
        
        # 그룹 ID가 지정된 경우, 해당 그룹의 태그 ID 조회
        group_tag_ids: set[UUID] = set()
        if group_ids:
            statement = select(Tag.id).where(Tag.group_id.in_(group_ids))
            group_tag_ids = set(self.session.exec(statement).all())
        
        # Todo별 태그 조회 (N+1 방지)
        todo_ids = [t.id for t in todos]
        statement = (
            select(ScheduleTag.schedule_id, ScheduleTag.tag_id)
            .where(ScheduleTag.schedule_id.in_(todo_ids))
        )
        todo_tag_rows = self.session.exec(statement).all()
        
        # Todo별 태그 매핑
        todo_tag_map: dict[UUID, set[UUID]] = {}
        for todo_id, tag_id in todo_tag_rows:
            if todo_id not in todo_tag_map:
                todo_tag_map[todo_id] = set()
            todo_tag_map[todo_id].add(tag_id)
        
        filtered_todos = []
        for todo in todos:
            todo_tags = todo_tag_map.get(todo.id, set())
            
            # 그룹 필터링
            if group_ids:
                if not todo_tags.intersection(group_tag_ids):
                    continue
            
            # 태그 필터링 (AND 방식)
            if tag_ids:
                if not set(tag_ids).issubset(todo_tags):
                    continue
            
            filtered_todos.append(todo)
        
        return filtered_todos

    def update_todo(self, todo_id: UUID, data: TodoUpdate) -> Todo:
        """
        Todo 업데이트
        
        비즈니스 로직:
        - Todo를 일정으로 변환하려면 is_todo=false와 함께 마감 시간이 필요
        - 마감 시간이 없는 Todo(917초)는 변환 시 start_time/end_time 필수
        
        :param todo_id: Todo ID
        :param data: 업데이트 데이터
        :return: 업데이트된 Todo
        :raises TodoNotFoundError: Todo를 찾을 수 없는 경우
        :raises NotATodoError: 일정이 Todo가 아닌 경우
        :raises DeadlineRequiredForConversionError: Todo를 일정으로 변환할 때 마감 시간이 없는 경우
        """
        todo = self.get_todo(todo_id)
        
        # 업데이트 데이터 준비
        update_dict = data.model_dump(exclude_unset=True)
        
        # Todo -> 일정 변환 검증
        is_converting_to_schedule = update_dict.get('is_todo') is False
        if is_converting_to_schedule:
            # 현재 Todo의 start_time이 917초인지 확인
            has_no_deadline = todo.start_time == TODO_DATETIME
            
            # 새로 전달된 start_time/end_time 확인
            new_start_time = update_dict.get('start_time')
            new_end_time = update_dict.get('end_time')
            
            # 마감 시간이 없는 Todo를 일정으로 변환하려면 새 마감 시간이 필수
            if has_no_deadline and (new_start_time is None or new_end_time is None):
                raise DeadlineRequiredForConversionError()
        
        # 태그 업데이트 (tag_ids가 설정된 경우에만)
        tag_ids_updated = 'tag_ids' in update_dict
        if tag_ids_updated:
            from app.domain.tag.service import TagService
            tag_service = TagService(self.session)
            tag_service.set_schedule_tags(todo.id, update_dict['tag_ids'] or [])
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
        
        :param todo_id: Todo ID
        :raises TodoNotFoundError: Todo를 찾을 수 없는 경우
        :raises NotATodoError: 일정이 Todo가 아닌 경우
        """
        todo = self.get_todo(todo_id)
        schedule_crud.delete_schedule(self.session, todo)

    def get_todo_tags(self, todo_id: UUID) -> List[Tag]:
        """
        Todo의 태그 조회
        
        :param todo_id: Todo ID
        :return: 태그 리스트
        """
        statement = (
            select(Tag)
            .join(ScheduleTag)
            .where(ScheduleTag.schedule_id == todo_id)
            .order_by(Tag.name)
        )
        return list(self.session.exec(statement).all())

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
            select(ScheduleTag.tag_id, Tag.name)
            .join(Tag)
            .where(ScheduleTag.schedule_id.in_(todo_ids))
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
        return TodoRead.from_schedule(todo, tags=tag_reads)
