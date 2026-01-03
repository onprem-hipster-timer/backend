"""
Tag Router

FastAPI Best Practices:
- 모든 라우트는 async
- Service는 session을 받아서 CRUD 직접 사용

Note: Schedule-Tag 관계는 Schedule 생성/수정 시 tag_ids 필드로 처리됩니다.
      ScheduleException-Tag 관계는 반복 일정 인스턴스 수정 시 tag_ids 필드로 처리됩니다.
"""
from typing import List

from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from app.db.session import get_db_transactional
from app.domain.tag.dependencies import valid_tag_group_id, valid_tag_id
from app.domain.tag.model import Tag, TagGroup
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
):
    """태그 그룹 생성"""
    service = TagService(session)
    return service.create_tag_group(data)


@router.get("/groups", response_model=List[TagGroupReadWithTags])
async def read_tag_groups(
        session: Session = Depends(get_db_transactional),
):
    """모든 태그 그룹 조회 (태그 포함)"""
    service = TagService(session)
    return service.get_all_tag_groups()


@router.get("/groups/{group_id}", response_model=TagGroupReadWithTags)
async def read_tag_group(
        tag_group: TagGroup = Depends(valid_tag_group_id),
        session: Session = Depends(get_db_transactional),
):
    """태그 그룹 조회 (태그 포함)"""
    # ORM 모델의 relationship이 자동으로 태그를 포함
    return tag_group


@router.patch("/groups/{group_id}", response_model=TagGroupRead)
async def update_tag_group(
        tag_group: TagGroup = Depends(valid_tag_group_id),
        data: TagGroupUpdate = ...,
        session: Session = Depends(get_db_transactional),
):
    """태그 그룹 업데이트"""
    service = TagService(session)
    return service.update_tag_group(tag_group.id, data)


@router.delete("/groups/{group_id}", status_code=status.HTTP_200_OK)
async def delete_tag_group(
        tag_group: TagGroup = Depends(valid_tag_group_id),
        session: Session = Depends(get_db_transactional),
):
    """태그 그룹 삭제 (CASCADE로 태그도 삭제)"""
    service = TagService(session)
    service.delete_tag_group(tag_group.id)
    return {"ok": True}


# ============================================================
# Tag Endpoints
# ============================================================

@router.post("", response_model=TagRead, status_code=status.HTTP_201_CREATED)
async def create_tag(
        data: TagCreate,
        session: Session = Depends(get_db_transactional),
):
    """태그 생성"""
    service = TagService(session)
    return service.create_tag(data)


@router.get("", response_model=List[TagRead])
async def read_tags(
        session: Session = Depends(get_db_transactional),
):
    """모든 태그 조회"""
    service = TagService(session)
    return service.get_all_tags()


@router.get("/{tag_id}", response_model=TagRead)
async def read_tag(
        tag: Tag = Depends(valid_tag_id),
):
    """태그 조회"""
    return TagRead.model_validate(tag)


@router.patch("/{tag_id}", response_model=TagRead)
async def update_tag(
        tag: Tag = Depends(valid_tag_id),
        data: TagUpdate = ...,
        session: Session = Depends(get_db_transactional),
):
    """태그 업데이트"""
    service = TagService(session)
    return service.update_tag(tag.id, data)


@router.delete("/{tag_id}", status_code=status.HTTP_200_OK)
async def delete_tag(
        tag: Tag = Depends(valid_tag_id),
        session: Session = Depends(get_db_transactional),
):
    """태그 삭제"""
    service = TagService(session)
    service.delete_tag(tag.id)
    return {"ok": True}

