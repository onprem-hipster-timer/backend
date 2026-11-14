"""
Guest CRUD Operations

- CRUD는 단순 데이터베이스 작업만 수행
- 비즈니스 로직은 app/domain/guest/service.py에서 처리
"""
from uuid import UUID

from sqlmodel import Session, select

from app.models.guest import Guest
from app.models.visibility import ResourceType


def create_guest(session: Session, guest: Guest) -> Guest:
    session.add(guest)
    session.flush()
    session.refresh(guest)
    return guest


def get_guest_by_identity(session: Session, identity_id: str) -> Guest | None:
    return session.exec(select(Guest).where(Guest.identity_id == identity_id)).first()


def list_resource_guests(session: Session, resource_type: ResourceType, resource_id: UUID) -> list[Guest]:
    """리소스의 게스트를 만든 순서대로"""
    statement = (
        select(Guest)
        .where(Guest.resource_type == resource_type)
        .where(Guest.resource_id == resource_id)
        .order_by(Guest.created_at, Guest.id)
    )
    return list(session.exec(statement).all())


def delete_guest(session: Session, guest: Guest) -> None:
    session.delete(guest)
    session.flush()
