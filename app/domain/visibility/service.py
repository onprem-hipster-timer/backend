"""
Visibility Service

리소스 가시성 비즈니스 로직 및 접근 제어

중앙 집중식 권한 검증 서비스:
- 모든 리소스의 가시성 체크를 이 서비스에서 처리
- ReBAC + ABAC 패턴 적용
"""
from typing import Optional, List, TypeVar
from uuid import UUID

from sqlmodel import Session

from app.core.auth import CurrentUser
from app.crud import friendship as friendship_crud
from app.crud import visibility as crud
from app.domain.visibility.enums import VisibilityLevel, ResourceType
from app.domain.visibility.exceptions import (
    AccessDeniedError,
    VisibilityNotFoundError,
    CannotShareWithNonFriendError,
)
from app.domain.visibility.model import ResourceVisibility
from app.domain.visibility.schema.dto import VisibilityRead

T = TypeVar("T")


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

        if level == VisibilityLevel.ALLOWED_EMAILS:
            # 현재 사용자의 이메일 확인 (OIDC 클레임에서 추출)
            user_email = self.current_user.email
            if not user_email:
                return False
            # 이메일 허용 목록 확인
            return crud.is_email_allowed(self.session, visibility.id, user_email)

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
            allowed_emails: Optional[List[str]] = None,
            allowed_domains: Optional[List[str]] = None,
    ) -> ResourceVisibility:
        """
        리소스 가시성 설정

        :param resource_type: 리소스 타입
        :param resource_id: 리소스 ID
        :param level: 가시성 레벨
        :param allowed_user_ids: 허용할 사용자 ID 목록 (SELECTED_FRIENDS 레벨에서만 사용)
        :param allowed_emails: 허용할 이메일 주소 목록 (ALLOWED_EMAILS 레벨에서만 사용)
        :param allowed_domains: 허용할 도메인 목록 (ALLOWED_EMAILS 레벨에서만 사용)
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
        if level == VisibilityLevel.SELECTED_FRIENDS:
            if allowed_user_ids:
                crud.set_allow_list(self.session, visibility.id, allowed_user_ids)
            else:
                crud.clear_allow_list(self.session, visibility.id)
            # 이메일 허용 목록 삭제 (레벨 변경 시)
            crud.clear_email_allow_list(self.session, visibility.id)
        elif level == VisibilityLevel.ALLOWED_EMAILS:
            # 이메일 허용 목록 설정
            if allowed_emails or allowed_domains:
                crud.set_email_allow_list(
                    self.session,
                    visibility.id,
                    allowed_emails=allowed_emails,
                    allowed_domains=allowed_domains,
                )
            else:
                crud.clear_email_allow_list(self.session, visibility.id)
            # 사용자 ID 허용 목록 삭제 (레벨 변경 시)
            crud.clear_allow_list(self.session, visibility.id)
        else:
            # 다른 레벨로 변경된 경우 모든 허용 목록 삭제
            crud.clear_allow_list(self.session, visibility.id)
            crud.clear_email_allow_list(self.session, visibility.id)

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

        # 이메일 허용 목록 조회
        email_entries = crud.get_email_allow_list(self.session, visibility.id)
        allowed_emails = [e.email for e in email_entries if e.email]
        allowed_domains = [e.domain for e in email_entries if e.domain]

        return VisibilityRead(
            id=visibility.id,
            resource_type=visibility.resource_type,
            resource_id=visibility.resource_id,
            owner_id=visibility.owner_id,
            level=visibility.level,
            allowed_user_ids=allowed_user_ids,
            allowed_emails=allowed_emails,
            allowed_domains=allowed_domains,
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

    def filter_accessible_resources(
            self,
            resource_type: ResourceType,
            visibilities: List[ResourceVisibility],
            resources: List[T],
            get_resource_id: callable,
    ) -> List[T]:
        """
        접근 가능한 리소스만 필터링 (배치)
        
        N+1 문제를 방지하기 위해 친구/차단 목록을 한 번에 조회하고
        배치로 권한 체크를 수행합니다.
        
        :param resource_type: 리소스 타입
        :param visibilities: 가시성 설정 목록 (미리 조회됨)
        :param resources: 필터링할 리소스 목록
        :param get_resource_id: 리소스에서 ID를 추출하는 함수 (lambda r: r.id)
        :return: 접근 가능한 리소스 리스트
        """
        if not resources:
            return []

        # 1. 친구 목록 한 번에 조회 (캐싱)
        friend_ids = set(friendship_crud.get_friend_ids(self.session, self.user_id))

        # 2. 차단 목록 한 번에 조회 (내가 차단한 + 나를 차단한)
        blocked_by_me = set()
        blocked_me = set()
        for f in friendship_crud.get_blocked_users(self.session, self.user_id):
            # 내가 차단한 사용자
            if f.requester_id == self.user_id:
                blocked_by_me.add(f.addressee_id)
            else:
                blocked_by_me.add(f.requester_id)

        # 나를 차단한 사용자들 조회를 위해 모든 owner_id에 대해 확인
        owner_ids = {v.owner_id for v in visibilities}
        for owner_id in owner_ids:
            if friendship_crud.is_blocked(self.session, owner_id, self.user_id):
                blocked_me.add(owner_id)

        # 3. visibility를 resource_id로 매핑
        visibility_map: dict[UUID, ResourceVisibility] = {
            v.resource_id: v for v in visibilities
        }

        # 4. 각 리소스의 owner_id 매핑 (visibility에서 추출)
        owner_map: dict[UUID, str] = {
            v.resource_id: v.owner_id for v in visibilities
        }

        # 5. AllowList 일괄 조회 (SELECTED_FRIENDS인 경우만)
        selected_friend_visibility_ids = [
            v.id for v in visibilities
            if v.level == VisibilityLevel.SELECTED_FRIENDS
        ]
        allow_list_map: dict[UUID, set[str]] = {}
        for v_id in selected_friend_visibility_ids:
            allow_list_map[v_id] = set(crud.get_allowed_user_ids(self.session, v_id))

        # 5-1. 이메일 허용 목록 일괄 조회 (ALLOWED_EMAILS인 경우만)
        allowed_email_visibility_ids = [
            v.id for v in visibilities
            if v.level == VisibilityLevel.ALLOWED_EMAILS
        ]
        email_allow_list_map: dict[UUID, list] = {}  # {visibility_id: [email_entries]}
        user_email = self.current_user.email
        user_email_domain = user_email.split("@")[-1] if user_email and "@" in user_email else None

        for v_id in allowed_email_visibility_ids:
            email_entries = crud.get_email_allow_list(self.session, v_id)
            email_allow_list_map[v_id] = email_entries

        # 6. 배치 권한 체크
        accessible_resources = []
        for resource in resources:
            resource_id = get_resource_id(resource)
            visibility = visibility_map.get(resource_id)

            if not visibility:
                continue

            owner_id = owner_map.get(resource_id)
            if not owner_id:
                continue

            # 소유자는 항상 접근 가능
            if owner_id == self.user_id:
                accessible_resources.append(resource)
                continue

            # 차단 관계 확인
            if owner_id in blocked_by_me or owner_id in blocked_me:
                continue

            # 가시성 레벨에 따른 접근 제어
            level = visibility.level

            if level == VisibilityLevel.PUBLIC:
                accessible_resources.append(resource)
            elif level == VisibilityLevel.FRIENDS:
                if owner_id in friend_ids:
                    accessible_resources.append(resource)
            elif level == VisibilityLevel.SELECTED_FRIENDS:
                if owner_id in friend_ids:
                    allowed = allow_list_map.get(visibility.id, set())
                    if self.user_id in allowed:
                        accessible_resources.append(resource)
            elif level == VisibilityLevel.ALLOWED_EMAILS:
                # 이메일 기반 접근 제어
                if user_email:
                    email_entries = email_allow_list_map.get(visibility.id, [])
                    is_allowed = False
                    for entry in email_entries:
                        # 특정 이메일 매칭
                        if entry.email and entry.email == user_email:
                            is_allowed = True
                            break
                        # 도메인 매칭
                        if entry.domain and user_email_domain and entry.domain == user_email_domain:
                            is_allowed = True
                            break
                    if is_allowed:
                        accessible_resources.append(resource)
            # PRIVATE은 이미 get_shared_visibilities에서 제외됨

        return accessible_resources
