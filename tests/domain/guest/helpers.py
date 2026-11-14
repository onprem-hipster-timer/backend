"""게스트 테스트에서 게스트 행과 identity를 바로 만드는 도우미"""
import uuid
from uuid import UUID

from app.db.session import _session_manager
from app.domain.guest.model import Guest
from app.models.visibility import ResourceType
from tests.domain.guest.fakes import FakeKratos


def make_guest(
        kratos: FakeKratos,
        resource_id: UUID,
        name: str = "민수",
        password: str = "1234",
        resource_type: ResourceType = ResourceType.MEETING,
) -> Guest:
    identity = kratos.add_identity("guest", {"handle": str(uuid.uuid4()), "name": name}, password)
    guest = Guest(identity_id=identity["id"], resource_type=resource_type, resource_id=resource_id)
    with _session_manager.get_session() as session:
        session.add(guest)
        session.commit()
        session.refresh(guest)
        session.expunge(guest)
    return guest


def guest_rows() -> list[Guest]:
    from sqlmodel import select

    with _session_manager.get_session() as session:
        rows = list(session.exec(select(Guest)).all())
        for row in rows:
            session.expunge(row)
        return rows
