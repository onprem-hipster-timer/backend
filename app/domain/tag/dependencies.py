"""
Tag Dependencies

FastAPI Best Practices:
- Dependencies를 활용한 데이터 검증
- Chain Dependencies로 코드 재사용
- valid_tag_id, valid_tag_group_id 패턴으로 중복 제거
"""
from uuid import UUID

from fastapi import Depends
from sqlmodel import Session

from app.crud import tag as crud
from app.db.session import get_db
from app.domain.tag.exceptions import TagGroupNotFoundError, TagNotFoundError
from app.domain.tag.model import TagGroup, Tag


async def valid_tag_group_id(
        group_id: UUID,
        session: Session = Depends(get_db),
) -> TagGroup:
    """
    TagGroup ID 검증 및 TagGroup 반환

    FastAPI Best Practices:
    - Dependency로 데이터 검증
    - 여러 엔드포인트에서 재사용 가능
    - FastAPI가 결과를 캐싱하여 중복 호출 방지
    - 읽기 전용이므로 get_db 사용 (commit 불필요)

    :param group_id: TagGroup ID
    :param session: DB 세션
    :return: TagGroup 객체
    :raises TagGroupNotFoundError: 태그 그룹을 찾을 수 없는 경우
    """
    tag_group = crud.get_tag_group(session, group_id)
    if not tag_group:
        raise TagGroupNotFoundError()
    return tag_group


async def valid_tag_id(
        tag_id: UUID,
        session: Session = Depends(get_db),
) -> Tag:
    """
    Tag ID 검증 및 Tag 반환

    FastAPI Best Practices:
    - Dependency로 데이터 검증
    - 여러 엔드포인트에서 재사용 가능
    - FastAPI가 결과를 캐싱하여 중복 호출 방지
    - 읽기 전용이므로 get_db 사용 (commit 불필요)

    :param tag_id: Tag ID
    :param session: DB 세션
    :return: Tag 객체
    :raises TagNotFoundError: 태그를 찾을 수 없는 경우
    """
    tag = crud.get_tag(session, tag_id)
    if not tag:
        raise TagNotFoundError()
    return tag


