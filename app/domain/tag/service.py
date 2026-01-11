"""
Tag Domain Service

FastAPI Best Practices:
- Service는 비즈니스 로직을 담당
- CRUD 함수를 직접 사용 (Repository 패턴 제거)
- Domain Exception을 발생시켜 비즈니스 규칙 위반 표현
- ORM 모델 반환 (API 레이어에서 DTO 변환)
"""
from typing import List
from uuid import UUID

from sqlmodel import Session

from app.crud import tag as crud
from app.domain.tag.exceptions import (
    TagGroupNotFoundError,
    TagNotFoundError,
    DuplicateTagNameError,
)
from app.domain.tag.model import TagGroup, Tag
from app.domain.tag.schema.dto import TagGroupCreate, TagGroupUpdate, TagCreate, TagUpdate


def _raise_group_not_found(group_id: UUID) -> None:
    """태그 그룹 없음 예외 발생 (상세 정보 포함)"""
    raise TagGroupNotFoundError(f"태그 그룹을 찾을 수 없습니다: {group_id}")


def _raise_tag_not_found(tag_id: UUID) -> None:
    """태그 없음 예외 발생 (상세 정보 포함)"""
    raise TagNotFoundError(f"태그를 찾을 수 없습니다: {tag_id}")


def _raise_duplicate_tag_name(group_id: UUID, tag_name: str) -> None:
    """태그 이름 중복 예외 발생 (상세 정보 포함)"""
    raise DuplicateTagNameError(f"그룹 내 태그 이름이 중복됩니다: {tag_name} (그룹: {group_id})")


class TagService:
    """태그 도메인 서비스"""

    def __init__(self, session: Session):
        self.session = session

    # ============================================================
    # TagGroup CRUD
    # ============================================================

    def create_tag_group(self, data: TagGroupCreate) -> TagGroup:
        """태그 그룹 생성"""
        tag_group = TagGroup.model_validate(data)
        return crud.create_tag_group(self.session, tag_group)

    def get_tag_group(self, group_id: UUID) -> TagGroup:
        """태그 그룹 조회"""
        tag_group = crud.get_tag_group(self.session, group_id)
        if not tag_group:
            _raise_group_not_found(group_id)
        return tag_group

    def get_all_tag_groups(self) -> List[TagGroup]:
        """모든 태그 그룹 조회"""
        return crud.get_all_tag_groups(self.session)

    def update_tag_group(self, group_id: UUID, data: TagGroupUpdate) -> TagGroup:
        """태그 그룹 업데이트"""
        tag_group = crud.get_tag_group(self.session, group_id)
        if not tag_group:
            _raise_group_not_found(group_id)

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(tag_group, key, value)

        return crud.update_tag_group(self.session, tag_group)

    def delete_tag_group(self, group_id: UUID) -> None:
        """
        태그 그룹 삭제
        
        비즈니스 로직:
        - Todo: 삭제 (그룹 필수이므로)
        - 일정: tag_group_id를 NULL로만 설정 (삭제 안 함)
        - 태그: CASCADE로 자동 삭제
        """
        tag_group = crud.get_tag_group(self.session, group_id)
        if not tag_group:
            _raise_group_not_found(group_id)

        # 1. 해당 그룹의 Todo 삭제 (Todo 모델 직접 사용)
        from app.domain.todo.service import TodoService

        todo_service = TodoService(self.session)
        result = todo_service.get_all_todos(group_ids=[group_id])
        for todo in result.todos:
            todo_service.delete_todo(todo.id)

        # 2. 일정의 tag_group_id를 NULL로 설정
        from app.crud import schedule as schedule_crud
        schedule_crud.clear_tag_group_id_from_schedules(self.session, group_id)

        # 3. 그룹 삭제 (태그는 CASCADE로 자동 삭제)
        crud.delete_tag_group(self.session, tag_group)

    # ============================================================
    # Tag CRUD
    # ============================================================

    def create_tag(self, data: TagCreate) -> Tag:
        """태그 생성"""
        # 그룹 존재 확인
        tag_group = crud.get_tag_group(self.session, data.group_id)
        if not tag_group:
            _raise_group_not_found(data.group_id)

        # 그룹 내 태그 이름 중복 확인
        existing = crud.get_tag_by_name_in_group(self.session, data.group_id, data.name)
        if existing:
            _raise_duplicate_tag_name(data.group_id, data.name)

        tag = Tag.model_validate(data)
        return crud.create_tag(self.session, tag)

    def get_tag(self, tag_id: UUID) -> Tag:
        """태그 조회"""
        tag = crud.get_tag(self.session, tag_id)
        if not tag:
            _raise_tag_not_found(tag_id)
        return tag

    def get_tags_by_group(self, group_id: UUID) -> List[Tag]:
        """그룹별 태그 조회"""
        # 그룹 존재 확인
        tag_group = crud.get_tag_group(self.session, group_id)
        if not tag_group:
            _raise_group_not_found(group_id)

        return crud.get_tags_by_group(self.session, group_id)

    def get_all_tags(self) -> List[Tag]:
        """모든 태그 조회"""
        return crud.get_all_tags(self.session)

    def update_tag(self, tag_id: UUID, data: TagUpdate) -> Tag:
        """태그 업데이트"""
        tag = crud.get_tag(self.session, tag_id)
        if not tag:
            _raise_tag_not_found(tag_id)

        # 이름 변경 시 중복 확인
        if data.name is not None and data.name != tag.name:
            existing = crud.get_tag_by_name_in_group(self.session, tag.group_id, data.name)
            if existing:
                _raise_duplicate_tag_name(tag.group_id, data.name)

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(tag, key, value)

        return crud.update_tag(self.session, tag)

    def delete_tag(self, tag_id: UUID) -> None:
        """
        태그 삭제 (일정에서 태그 연결만 제거, 일정은 유지)
        
        모든 태그가 삭제되었으면 그룹도 자동 삭제됩니다.
        """
        tag = crud.get_tag(self.session, tag_id)
        if not tag:
            _raise_tag_not_found(tag_id)

        group_id = tag.group_id
        crud.delete_tag(self.session, tag)

        # 모든 태그가 삭제되었는지 확인 (반복 일정 패턴과 동일)
        if self._are_all_tags_deleted(group_id):
            # 모든 태그가 삭제되었으면 그룹도 삭제
            group = crud.get_tag_group(self.session, group_id)
            if group:
                crud.delete_tag_group(self.session, group)

    def _are_all_tags_deleted(self, group_id: UUID) -> bool:
        """
        그룹의 모든 태그가 삭제되었는지 확인
        
        반복 일정의 _are_all_instances_deleted 패턴과 동일합니다.
        
        :param group_id: 태그 그룹 ID
        :return: 모든 태그가 삭제되었으면 True
        """
        remaining_tags = crud.get_tags_by_group(self.session, group_id)
        return len(remaining_tags) == 0

    # ============================================================
    # Schedule-Tag 관계 관리
    # ============================================================

    def add_tag_to_schedule(self, schedule_id: UUID, tag_id: UUID) -> None:
        """일정에 태그 추가"""
        # 태그 존재 확인
        tag = crud.get_tag(self.session, tag_id)
        if not tag:
            _raise_tag_not_found(tag_id)

        # 이미 연결되어 있는지 확인
        existing = crud.get_schedule_tag(self.session, schedule_id, tag_id)
        if existing:
            return  # 이미 연결됨

        crud.add_schedule_tag(self.session, schedule_id, tag_id)

    def remove_tag_from_schedule(self, schedule_id: UUID, tag_id: UUID) -> None:
        """일정에서 태그 제거"""
        schedule_tag = crud.get_schedule_tag(self.session, schedule_id, tag_id)
        if schedule_tag:
            crud.delete_schedule_tag(self.session, schedule_tag)

    def get_schedule_tags(self, schedule_id: UUID) -> List[Tag]:
        """일정의 태그 조회"""
        return crud.get_schedule_tags(self.session, schedule_id)

    def set_schedule_tags(self, schedule_id: UUID, tag_ids: List[UUID]) -> List[Tag]:
        """일정의 태그 일괄 설정 (기존 태그 교체)"""
        # 태그 존재 확인
        for tag_id in tag_ids:
            tag = crud.get_tag(self.session, tag_id)
            if not tag:
                _raise_tag_not_found(tag_id)

        # 기존 태그 연결 삭제
        crud.delete_all_schedule_tags(self.session, schedule_id)

        # 새 태그 연결
        for tag_id in tag_ids:
            crud.add_schedule_tag(self.session, schedule_id, tag_id)

        return self.get_schedule_tags(schedule_id)

    # ============================================================
    # ScheduleException-Tag 관계 관리
    # ============================================================

    def add_tag_to_schedule_exception(self, exception_id: UUID, tag_id: UUID) -> None:
        """예외 일정에 태그 추가"""
        tag = crud.get_tag(self.session, tag_id)
        if not tag:
            _raise_tag_not_found(tag_id)

        existing = crud.get_schedule_exception_tag(self.session, exception_id, tag_id)
        if existing:
            return

        crud.add_schedule_exception_tag(self.session, exception_id, tag_id)

    def remove_tag_from_schedule_exception(self, exception_id: UUID, tag_id: UUID) -> None:
        """예외 일정에서 태그 제거"""
        exception_tag = crud.get_schedule_exception_tag(self.session, exception_id, tag_id)
        if exception_tag:
            crud.delete_schedule_exception_tag(self.session, exception_tag)

    def get_schedule_exception_tags(self, exception_id: UUID) -> List[Tag]:
        """예외 일정의 태그 조회"""
        return crud.get_schedule_exception_tags(self.session, exception_id)

    def set_schedule_exception_tags(self, exception_id: UUID, tag_ids: List[UUID]) -> List[Tag]:
        """예외 일정의 태그 일괄 설정"""
        # 태그 존재 확인
        for tag_id in tag_ids:
            tag = crud.get_tag(self.session, tag_id)
            if not tag:
                _raise_tag_not_found(tag_id)

        # 기존 태그 연결 삭제
        crud.delete_all_schedule_exception_tags(self.session, exception_id)

        # 새 태그 연결
        for tag_id in tag_ids:
            crud.add_schedule_exception_tag(self.session, exception_id, tag_id)

        return self.get_schedule_exception_tags(exception_id)

    # ============================================================
    # Timer-Tag 관계 관리
    # ============================================================

    def add_tag_to_timer(self, timer_id: UUID, tag_id: UUID) -> None:
        """타이머에 태그 추가"""
        # 태그 존재 확인
        tag = crud.get_tag(self.session, tag_id)
        if not tag:
            _raise_tag_not_found(tag_id)

        # 이미 연결되어 있는지 확인
        existing = crud.get_timer_tag(self.session, timer_id, tag_id)
        if existing:
            return  # 이미 연결됨

        crud.add_timer_tag(self.session, timer_id, tag_id)

    def remove_tag_from_timer(self, timer_id: UUID, tag_id: UUID) -> None:
        """타이머에서 태그 제거"""
        timer_tag = crud.get_timer_tag(self.session, timer_id, tag_id)
        if timer_tag:
            crud.delete_timer_tag(self.session, timer_tag)

    def get_timer_tags(self, timer_id: UUID) -> List[Tag]:
        """타이머의 태그 조회"""
        return crud.get_timer_tags(self.session, timer_id)

    def set_timer_tags(self, timer_id: UUID, tag_ids: List[UUID]) -> List[Tag]:
        """타이머의 태그 일괄 설정 (기존 태그 교체)"""
        # 태그 존재 확인
        for tag_id in tag_ids:
            tag = crud.get_tag(self.session, tag_id)
            if not tag:
                _raise_tag_not_found(tag_id)

        # 기존 태그 연결 삭제
        crud.delete_all_timer_tags(self.session, timer_id)

        # 새 태그 연결
        for tag_id in tag_ids:
            crud.add_timer_tag(self.session, timer_id, tag_id)

        return self.get_timer_tags(timer_id)

    # ============================================================
    # Todo-Tag 관계 관리
    # ============================================================

    def add_tag_to_todo(self, todo_id: UUID, tag_id: UUID) -> None:
        """Todo에 태그 추가"""
        # 태그 존재 확인
        tag = crud.get_tag(self.session, tag_id)
        if not tag:
            _raise_tag_not_found(tag_id)

        # 이미 연결되어 있는지 확인
        existing = crud.get_todo_tag(self.session, todo_id, tag_id)
        if existing:
            return  # 이미 연결됨

        crud.add_todo_tag(self.session, todo_id, tag_id)

    def remove_tag_from_todo(self, todo_id: UUID, tag_id: UUID) -> None:
        """Todo에서 태그 제거"""
        todo_tag = crud.get_todo_tag(self.session, todo_id, tag_id)
        if todo_tag:
            crud.delete_todo_tag(self.session, todo_tag)

    def get_todo_tags(self, todo_id: UUID) -> List[Tag]:
        """Todo의 태그 조회"""
        return crud.get_todo_tags(self.session, todo_id)

    def set_todo_tags(self, todo_id: UUID, tag_ids: List[UUID]) -> List[Tag]:
        """Todo의 태그 일괄 설정 (기존 태그 교체)"""
        # 태그 존재 확인
        for tag_id in tag_ids:
            tag = crud.get_tag(self.session, tag_id)
            if not tag:
                _raise_tag_not_found(tag_id)

        # 기존 태그 연결 삭제
        crud.delete_all_todo_tags(self.session, todo_id)

        # 새 태그 연결
        for tag_id in tag_ids:
            crud.add_todo_tag(self.session, todo_id, tag_id)

        return self.get_todo_tags(todo_id)
