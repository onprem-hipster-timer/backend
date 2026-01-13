"""
Tag Router

FastAPI Best Practices:
- 모든 라우트는 async
- Service는 session을 받아서 CRUD 직접 사용

Note: Schedule-Tag 관계는 Schedule 생성/수정 시 tag_ids 필드로 처리됩니다.
      ScheduleException-Tag 관계는 반복 일정 인스턴스 수정 시 tag_ids 필드로 처리됩니다.
"""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from app.core.auth import CurrentUser, get_current_user
from app.db.session import get_db_transactional
from app.domain.tag.schema.dto import (
    TagGroupCreate,
    TagGroupRead,
    TagGroupReadWithTags,
    TagGroupUpdate,
    TagCreate,
    TagRead,
    TagUpdate,
)
from app.domain.tag.service import TagService

router = APIRouter(prefix="/tags", tags=["Tags"])


# ============================================================
# TagGroup Endpoints
# ============================================================

@router.post("/groups", response_model=TagGroupRead, status_code=status.HTTP_201_CREATED)
async def create_tag_group(
        data: TagGroupCreate,
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """태그 그룹 생성"""
    service = TagService(session, current_user)
    return service.create_tag_group(data)


@router.get("/groups", response_model=List[TagGroupReadWithTags])
async def read_tag_groups(
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """모든 태그 그룹 조회 (태그 포함)"""
    service = TagService(session, current_user)
    return service.get_all_tag_groups()


@router.get("/groups/{group_id}", response_model=TagGroupReadWithTags)
async def read_tag_group(
        group_id: UUID,
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """태그 그룹 조회 (태그 포함)"""
    service = TagService(session, current_user)
    return service.get_tag_group(group_id)


@router.patch("/groups/{group_id}", response_model=TagGroupRead)
async def update_tag_group(
        group_id: UUID,
        data: TagGroupUpdate,
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """태그 그룹 업데이트"""
    service = TagService(session, current_user)
    return service.update_tag_group(group_id, data)


@router.delete("/groups/{group_id}", status_code=status.HTTP_200_OK)
async def delete_tag_group(
        group_id: UUID,
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """태그 그룹 삭제 (CASCADE로 태그도 삭제)"""
    service = TagService(session, current_user)
    service.delete_tag_group(group_id)
    return {"ok": True}


# ============================================================
# Tag Endpoints
# ============================================================

@router.post("", response_model=TagRead, status_code=status.HTTP_201_CREATED)
async def create_tag(
        data: TagCreate,
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """태그 생성"""
    service = TagService(session, current_user)
    return service.create_tag(data)


@router.get("", response_model=List[TagRead])
async def read_tags(
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """모든 태그 조회"""
    service = TagService(session, current_user)
    return service.get_all_tags()


@router.get("/{tag_id}", response_model=TagRead)
async def read_tag(
        tag_id: UUID,
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """태그 조회"""
    service = TagService(session, current_user)
    return service.get_tag(tag_id)


@router.patch("/{tag_id}", response_model=TagRead)
async def update_tag(
        tag_id: UUID,
        data: TagUpdate,
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """태그 업데이트"""
    service = TagService(session, current_user)
    return service.update_tag(tag_id, data)


@router.delete("/{tag_id}", status_code=status.HTTP_200_OK)
async def delete_tag(
        tag_id: UUID,
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """태그 삭제"""
    service = TagService(session, current_user)
    service.delete_tag(tag_id)
    return {"ok": True}
