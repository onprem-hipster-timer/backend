"""
Visibility CRUD 함수

리소스 가시성 데이터 접근 레이어
"""
from typing import Optional
from uuid import UUID

from sqlmodel import Session, select

from app.models.visibility import (
    ResourceVisibility,
    VisibilityAllowList,
    VisibilityLevel,
    ResourceType,
)


# ============================================================
# ResourceVisibility CRUD
# ============================================================

def create_visibility(
        session: Session,
        resource_type: ResourceType,
        resource_id: UUID,
        owner_id: str,
        level: VisibilityLevel = VisibilityLevel.PRIVATE,
) -> ResourceVisibility:
    """리소스 가시성 생성"""
    visibility = ResourceVisibility(
        resource_type=resource_type,
        resource_id=resource_id,
        owner_id=owner_id,
        level=level,
    )
    session.add(visibility)
    session.flush()
    session.refresh(visibility)
    return visibility


def get_visibility(
        session: Session,
        visibility_id: UUID,
) -> Optional[ResourceVisibility]:
    """ID로 가시성 조회"""
    return session.get(ResourceVisibility, visibility_id)


def get_visibility_by_resource(
        session: Session,
        resource_type: ResourceType,
        resource_id: UUID,
) -> Optional[ResourceVisibility]:
    """리소스로 가시성 조회"""
    statement = select(ResourceVisibility).where(
        ResourceVisibility.resource_type == resource_type,
        ResourceVisibility.resource_id == resource_id,
    )
    return session.exec(statement).first()


def get_visibilities_by_owner(
        session: Session,
        owner_id: str,
        resource_type: Optional[ResourceType] = None,
) -> list[ResourceVisibility]:
    """소유자의 가시성 설정 목록 조회"""
    statement = select(ResourceVisibility).where(
        ResourceVisibility.owner_id == owner_id,
    )
    if resource_type:
        statement = statement.where(ResourceVisibility.resource_type == resource_type)
    return list(session.exec(statement).all())


def update_visibility(
        session: Session,
        visibility: ResourceVisibility,
        level: VisibilityLevel,
) -> ResourceVisibility:
    """가시성 레벨 업데이트"""
    visibility.level = level
    session.flush()
    session.refresh(visibility)
    return visibility


def upsert_visibility(
        session: Session,
        resource_type: ResourceType,
        resource_id: UUID,
        owner_id: str,
        level: VisibilityLevel,
) -> ResourceVisibility:
    """가시성 생성 또는 업데이트"""
    visibility = get_visibility_by_resource(session, resource_type, resource_id)
    if visibility:
        return update_visibility(session, visibility, level)
    return create_visibility(session, resource_type, resource_id, owner_id, level)


def delete_visibility(session: Session, visibility: ResourceVisibility) -> None:
    """가시성 삭제 (AllowList도 CASCADE로 삭제됨)"""
    session.delete(visibility)
    session.flush()


def delete_visibility_by_resource(
        session: Session,
        resource_type: ResourceType,
        resource_id: UUID,
) -> bool:
    """리소스로 가시성 삭제"""
    visibility = get_visibility_by_resource(session, resource_type, resource_id)
    if visibility:
        delete_visibility(session, visibility)
        return True
    return False


# ============================================================
# VisibilityAllowList CRUD
# ============================================================

def add_to_allow_list(
        session: Session,
        visibility_id: UUID,
        allowed_user_id: str,
) -> VisibilityAllowList:
    """허용 목록에 사용자 추가"""
    entry = VisibilityAllowList(
        visibility_id=visibility_id,
        allowed_user_id=allowed_user_id,
    )
    session.add(entry)
    session.flush()
    session.refresh(entry)
    return entry


def get_allow_list(
        session: Session,
        visibility_id: UUID,
) -> list[VisibilityAllowList]:
    """허용 목록 조회"""
    statement = select(VisibilityAllowList).where(
        VisibilityAllowList.visibility_id == visibility_id,
    )
    return list(session.exec(statement).all())


def get_allowed_user_ids(
        session: Session,
        visibility_id: UUID,
) -> list[str]:
    """허용된 사용자 ID 목록 조회"""
    entries = get_allow_list(session, visibility_id)
    return [entry.allowed_user_id for entry in entries]


def is_user_in_allow_list(
        session: Session,
        visibility_id: UUID,
        user_id: str,
) -> bool:
    """사용자가 허용 목록에 있는지 확인"""
    statement = select(VisibilityAllowList).where(
        VisibilityAllowList.visibility_id == visibility_id,
        VisibilityAllowList.allowed_user_id == user_id,
    )
    return session.exec(statement).first() is not None


def remove_from_allow_list(
        session: Session,
        visibility_id: UUID,
        allowed_user_id: str,
) -> bool:
    """허용 목록에서 사용자 제거"""
    statement = select(VisibilityAllowList).where(
        VisibilityAllowList.visibility_id == visibility_id,
        VisibilityAllowList.allowed_user_id == allowed_user_id,
    )
    entry = session.exec(statement).first()
    if entry:
        session.delete(entry)
        session.flush()
        return True
    return False


def clear_allow_list(session: Session, visibility_id: UUID) -> int:
    """허용 목록 전체 삭제"""
    entries = get_allow_list(session, visibility_id)
    count = len(entries)
    for entry in entries:
        session.delete(entry)
    session.flush()
    return count


def set_allow_list(
        session: Session,
        visibility_id: UUID,
        allowed_user_ids: list[str],
) -> list[VisibilityAllowList]:
    """허용 목록 전체 설정 (기존 목록 교체)"""
    # 기존 목록 삭제
    clear_allow_list(session, visibility_id)

    # 새 목록 추가
    entries = []
    for user_id in allowed_user_ids:
        entry = add_to_allow_list(session, visibility_id, user_id)
        entries.append(entry)

    return entries


def remove_user_from_all_allow_lists(
        session: Session,
        owner_id: str,
        user_id: str,
) -> int:
    """
    특정 소유자의 모든 리소스 AllowList에서 사용자 제거
    
    친구 삭제 시 해당 친구가 포함된 모든 AllowList를 정리하기 위해 사용
    
    :param session: DB 세션
    :param owner_id: 리소스 소유자 ID
    :param user_id: 제거할 사용자 ID
    :return: 제거된 항목 수
    """
    statement = (
        select(VisibilityAllowList)
        .join(ResourceVisibility)
        .where(
            ResourceVisibility.owner_id == owner_id,
            VisibilityAllowList.allowed_user_id == user_id,
        )
    )
    entries = list(session.exec(statement).all())
    count = len(entries)
    for entry in entries:
        session.delete(entry)
    if count > 0:
        session.flush()
    return count


# ============================================================
# 공유 리소스 조회 (Shared Resource Query)
# ============================================================

def get_shared_visibilities(
        session: Session,
        resource_type: ResourceType,
        exclude_owner_id: str,
) -> list[ResourceVisibility]:
    """
    타인 소유의 공개된(visibility != PRIVATE) 리소스 가시성 목록 조회
    
    scope=shared 조회 시 사용. 반환된 목록에 대해 추가로 
    VisibilityService.can_access()로 실제 접근 가능 여부 확인 필요.
    
    :param session: DB 세션
    :param resource_type: 리소스 타입
    :param exclude_owner_id: 제외할 소유자 ID (본인)
    :return: 공개된 가시성 설정 목록
    """
    statement = (
        select(ResourceVisibility)
        .where(ResourceVisibility.resource_type == resource_type)
        .where(ResourceVisibility.owner_id != exclude_owner_id)
        .where(ResourceVisibility.level != VisibilityLevel.PRIVATE)
    )
    return list(session.exec(statement).all())


def get_shared_resource_ids(
        session: Session,
        resource_type: ResourceType,
        exclude_owner_id: str,
) -> list[tuple[UUID, str]]:
    """
    공유된 리소스 ID와 소유자 ID 튜플 목록 조회
    
    :param session: DB 세션
    :param resource_type: 리소스 타입
    :param exclude_owner_id: 제외할 소유자 ID (본인)
    :return: (resource_id, owner_id) 튜플 목록
    """
    visibilities = get_shared_visibilities(session, resource_type, exclude_owner_id)
    return [(v.resource_id, v.owner_id) for v in visibilities]
