"""
Visibility Service

리소스 가시성 비즈니스 로직 및 접근 제어

중앙 집중식 권한 검증 서비스:
- 모든 리소스의 가시성 체크를 이 서비스에서 처리
- ReBAC + ABAC 패턴 적용
"""
from typing import Optional, List
from uuid import UUID

from sqlmodel import Session

from app.core.auth import CurrentUser
from app.crud import visibility as crud
from app.crud import friendship as friendship_crud
from app.domain.visibility.enums import VisibilityLevel, ResourceType
from app.domain.visibility.exceptions import (
    AccessDeniedError,
    VisibilityNotFoundError,
    CannotShareWithNonFriendError,
)
from app.domain.visibility.model import ResourceVisibility
from app.domain.visibility.schema.dto import VisibilityRead


class VisibilityService:
    """
    Visibility Service - 리소스 가시성 비즈니스 로직

    핵심 기능:
    - 리소스 접근 권한 확인 (can_access)
    - 가시성 설정 관리 (set_visibility, get_visibility)
    - 접근 가능한 리소스 필터링

    접근 제어 로직:
    1. 소유자 → 항상 허용
    2. PUBLIC → 모든 사용자 허용
    3. FRIENDS → 친구만 허용
    4. SELECTED_FRIENDS → AllowList에 있는 사용자만 허용
    5. PRIVATE → 소유자만 허용
    """

    def __init__(self, session: Session, current_user: CurrentUser):
        self.session = session
        self.current_user = current_user
        self.user_id = current_user.sub

    def can_access(
        self,
        resource_type: ResourceType,
        resource_id: UUID,
        owner_id: str,
    ) -> bool:
        """
        리소스에 대한 접근 권한 확인

        :param resource_type: 리소스 타입
        :param resource_id: 리소스 ID
        :param owner_id: 리소스 소유자 ID
        :return: 접근 가능 여부
        """
        # 1. 소유자는 항상 접근 가능
        if self.user_id == owner_id:
            return True

        # 2. 차단 관계 확인 (양방향)
        if self._is_blocked_relation(owner_id):
            return False

        # 3. 가시성 설정 조회
        visibility = crud.get_visibility_by_resource(
            self.session,
            resource_type,
            resource_id,
        )

        # 가시성 설정이 없으면 PRIVATE으로 간주
        if not visibility:
            return False

        # 4. 가시성 레벨에 따른 접근 제어
        return self._check_visibility_level(visibility, owner_id)

    def _check_visibility_level(
        self,
        visibility: ResourceVisibility,
        owner_id: str,
    ) -> bool:
        """가시성 레벨에 따른 접근 권한 확인"""
        level = visibility.level

        if level == VisibilityLevel.PUBLIC:
            return True

        if level == VisibilityLevel.FRIENDS:
            return friendship_crud.is_friend(self.session, self.user_id, owner_id)

        if level == VisibilityLevel.SELECTED_FRIENDS:
            # 먼저 친구인지 확인
            if not friendship_crud.is_friend(self.session, self.user_id, owner_id):
                return False
            # AllowList에 있는지 확인
            return crud.is_user_in_allow_list(self.session, visibility.id, self.user_id)

        # PRIVATE
        return False

    def _is_blocked_relation(self, other_user_id: str) -> bool:
        """차단 관계 확인 (양방향)"""
        return (
            friendship_crud.is_blocked(self.session, self.user_id, other_user_id)
            or friendship_crud.is_blocked(self.session, other_user_id, self.user_id)
        )

    def require_access(
        self,
        resource_type: ResourceType,
        resource_id: UUID,
        owner_id: str,
    ) -> None:
        """
        리소스 접근 권한 확인 (없으면 예외 발생)

        :raises AccessDeniedError: 접근 권한이 없는 경우
        """
        if not self.can_access(resource_type, resource_id, owner_id):
            raise AccessDeniedError()

    def set_visibility(
        self,
        resource_type: ResourceType,
        resource_id: UUID,
        level: VisibilityLevel,
        allowed_user_ids: Optional[List[str]] = None,
    ) -> ResourceVisibility:
        """
        리소스 가시성 설정

        :param resource_type: 리소스 타입
        :param resource_id: 리소스 ID
        :param level: 가시성 레벨
        :param allowed_user_ids: 허용할 사용자 ID 목록 (SELECTED_FRIENDS 레벨에서만)
        :return: 생성/업데이트된 가시성 설정
        """
        # SELECTED_FRIENDS 레벨인 경우 검증
        if level == VisibilityLevel.SELECTED_FRIENDS:
            if allowed_user_ids:
                # 모든 사용자가 친구인지 확인
                for user_id in allowed_user_ids:
                    if not friendship_crud.is_friend(self.session, self.user_id, user_id):
                        raise CannotShareWithNonFriendError()

        # 가시성 설정 생성/업데이트
        visibility = crud.upsert_visibility(
            self.session,
            resource_type,
            resource_id,
            self.user_id,
            level,
        )

        # AllowList 설정 (SELECTED_FRIENDS 레벨인 경우)
        if level == VisibilityLevel.SELECTED_FRIENDS and allowed_user_ids:
            crud.set_allow_list(self.session, visibility.id, allowed_user_ids)
        elif level != VisibilityLevel.SELECTED_FRIENDS:
            # 다른 레벨로 변경된 경우 AllowList 삭제
            crud.clear_allow_list(self.session, visibility.id)

        return visibility

    def get_visibility(
        self,
        resource_type: ResourceType,
        resource_id: UUID,
    ) -> Optional[VisibilityRead]:
        """
        리소스 가시성 설정 조회

        :return: 가시성 설정 (없으면 None)
        """
        visibility = crud.get_visibility_by_resource(
            self.session,
            resource_type,
            resource_id,
        )

        if not visibility:
            return None

        # AllowList 조회
        allowed_user_ids = crud.get_allowed_user_ids(self.session, visibility.id)

        return VisibilityRead(
            id=visibility.id,
            resource_type=visibility.resource_type,
            resource_id=visibility.resource_id,
            owner_id=visibility.owner_id,
            level=visibility.level,
            allowed_user_ids=allowed_user_ids,
            created_at=visibility.created_at,
            updated_at=visibility.updated_at,
        )

    def delete_visibility(
        self,
        resource_type: ResourceType,
        resource_id: UUID,
    ) -> bool:
        """
        리소스 가시성 설정 삭제 (PRIVATE으로 복귀)

        :return: 삭제 성공 여부
        """
        return crud.delete_visibility_by_resource(
            self.session,
            resource_type,
            resource_id,
        )

    def get_accessible_resource_ids(
        self,
        resource_type: ResourceType,
        resource_ids: List[UUID],
        owner_ids: dict[UUID, str],
    ) -> List[UUID]:
        """
        접근 가능한 리소스 ID 필터링

        대량의 리소스에 대해 접근 권한을 확인할 때 사용

        :param resource_type: 리소스 타입
        :param resource_ids: 확인할 리소스 ID 목록
        :param owner_ids: 리소스 ID → 소유자 ID 매핑
        :return: 접근 가능한 리소스 ID 목록
        """
        accessible_ids = []

        for resource_id in resource_ids:
            owner_id = owner_ids.get(resource_id)
            if owner_id and self.can_access(resource_type, resource_id, owner_id):
                accessible_ids.append(resource_id)

        return accessible_ids

    def add_to_allow_list(
        self,
        resource_type: ResourceType,
        resource_id: UUID,
        user_id: str,
    ) -> None:
        """
        AllowList에 사용자 추가

        :param resource_type: 리소스 타입
        :param resource_id: 리소스 ID
        :param user_id: 추가할 사용자 ID
        """
        # 친구인지 확인
        if not friendship_crud.is_friend(self.session, self.user_id, user_id):
            raise CannotShareWithNonFriendError()

        visibility = crud.get_visibility_by_resource(
            self.session,
            resource_type,
            resource_id,
        )

        if not visibility:
            raise VisibilityNotFoundError()

        # AllowList에 추가
        if not crud.is_user_in_allow_list(self.session, visibility.id, user_id):
            crud.add_to_allow_list(self.session, visibility.id, user_id)

    def remove_from_allow_list(
        self,
        resource_type: ResourceType,
        resource_id: UUID,
        user_id: str,
    ) -> None:
        """
        AllowList에서 사용자 제거

        :param resource_type: 리소스 타입
        :param resource_id: 리소스 ID
        :param user_id: 제거할 사용자 ID
        """
        visibility = crud.get_visibility_by_resource(
            self.session,
            resource_type,
            resource_id,
        )

        if not visibility:
            raise VisibilityNotFoundError()

        crud.remove_from_allow_list(self.session, visibility.id, user_id)
