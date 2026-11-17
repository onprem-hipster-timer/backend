"""게스트 테스트에서 게스트 행과 identity를 바로 만드는 도우미"""
import uuid
from uuid import UUID

import app.core.config as app_config
from app.db.session import _session_manager
from app.domain.guest.model import Guest
from app.domain.guest.schema.dto import normalize_guest_name
from app.models.visibility import ResourceType
from tests.domain.guest.fakes import FakeKratos


def make_guest(
        kratos: FakeKratos,
        resource_id: UUID,
        name: str = "민수",
        password: str = "1234",
        resource_type: ResourceType = ResourceType.MEETING,
) -> Guest:
    """Kratos identity(handle "<행 id>@guest.invalid", trait name)와 게스트 행(name은 정규형)을 만든다"""
    guest_id = uuid.uuid4()
    identity = kratos.add_identity("guest", {"handle": f"{guest_id}@guest.invalid", "name": name}, password)
    guest = Guest(
        id=guest_id,
        identity_id=identity["id"],
        resource_type=resource_type,
        resource_id=resource_id,
        name=normalize_guest_name(name),
    )
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


def consent_body(version: str | None = None) -> dict:
    """POST /v1/guests의 consent, PUT /v1/guests/me/consent의 본문 (기본은 현재 약관 버전)"""
    return {
        "version": version or app_config.settings.CONSENT_VERSION,
        "age_over_14": True,
        "terms": True,
        "privacy": True,
    }


def consent_rows() -> set[tuple[str, str]]:
    """consent 테이블의 (sub, version)"""
    from sqlmodel import select

    from app.models.consent import Consent

    with _session_manager.get_session() as session:
        return {(c.sub, c.version) for c in session.exec(select(Consent)).all()}


def consent_analytics() -> dict[str, bool | None]:
    """현재 약관 버전 consent 행의 sub → 사용성 분석 동의(analytics)"""
    from sqlmodel import select

    from app.models.consent import Consent

    with _session_manager.get_session() as session:
        rows = session.exec(select(Consent).where(Consent.version == app_config.settings.CONSENT_VERSION)).all()
        return {c.sub: c.analytics for c in rows}
