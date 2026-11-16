"""
Guest CRUD Operations

- CRUD는 단순 데이터베이스 작업만 수행
- 비즈니스 로직은 app/domain/guest/service.py에서 처리
"""
from uuid import UUID

from sqlmodel import Session, func, select

from app.models.guest import Guest
from app.models.visibility import ResourceType


def create_guest(session: Session, guest: Guest) -> Guest:
    session.add(guest)
    session.flush()
    session.refresh(guest)
    return guest


def get_guest_by_identity(session: Session, identity_id: str, for_update: bool = False) -> Guest | None:
    """
    identity id로 게스트 조회

    for_update=True면 트랜잭션 끝까지 행을 잠그고(FOR NO KEY UPDATE, SQLite에서는 무시),
    세션에 이미 올라온 객체도 잠근 뒤의 DB 값으로 덮어쓴다.
    """
    statement = select(Guest).where(Guest.identity_id == identity_id)
    if for_update:
        statement = statement.with_for_update(key_share=True).execution_options(
            populate_existing=True
        )
    return session.exec(statement).first()


def get_guest_by_name(session: Session, resource_type: ResourceType, resource_id: UUID, name: str) -> Guest | None:
    statement = (
        select(Guest)
        .where(Guest.resource_type == resource_type)
        .where(Guest.resource_id == resource_id)
        .where(Guest.name == name)
    )
    return session.exec(statement).first()


def list_resource_guests(session: Session, resource_type: ResourceType, resource_id: UUID) -> list[Guest]:
    """리소스의 게스트를 만든 순서대로"""
    statement = (
        select(Guest)
        .where(Guest.resource_type == resource_type)
        .where(Guest.resource_id == resource_id)
        .order_by(Guest.created_at, Guest.id)
    )
    return list(session.exec(statement).all())


def count_resource_guests(session: Session, resource_type: ResourceType, resource_id: UUID) -> int:
    statement = (
        select(func.count())
        .select_from(Guest)
        .where(Guest.resource_type == resource_type)
        .where(Guest.resource_id == resource_id)
    )
    return session.exec(statement).one()


def delete_guest(session: Session, guest: Guest) -> None:
    session.delete(guest)
    session.flush()
