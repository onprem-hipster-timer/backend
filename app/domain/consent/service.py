"""
약관 동의 서비스

회원과 게스트가 함께 쓴다. 키는 Kratos identity id(JWT sub)이고, 현재 시행 중인 버전(settings.CONSENT_VERSION)에
동의한 행이 있으면 동의한 것이다. 버전마다 한 행을 남기고, 같은 버전에 다시 동의하면 처음 행을 그대로 둔다.

- 회원: 인증 의존성(app/core/auth/dependencies.py)과 GraphQL 컨텍스트의 428, PUT /v1/users/me/consent, 파기(app/domain/user/purge.py)

함수는 받은 세션에 쓰고 커밋하지 않는다.

테스트: tests/domain/consent/test_service.py
"""
from typing import Iterable

from sqlmodel import Session

import app.core.config as app_config
from app.crud import consent as crud
from app.domain.consent.exceptions import ConsentVersionMismatchError
from app.domain.consent.model import Consent
from app.domain.consent.schema.dto import ConsentCreate


def check_version(data: ConsentCreate) -> None:
    """현재 약관 버전이 아니면 ConsentVersionMismatchError"""
    if data.version != app_config.settings.CONSENT_VERSION:
        raise ConsentVersionMismatchError()


def consent_pending(session: Session, sub: str) -> bool:
    """sub가 현재 약관 버전에 동의하지 않았으면 True"""
    return crud.get_consent(session, sub, app_config.settings.CONSENT_VERSION) is None


def record_consent(session: Session, sub: str, data: ConsentCreate) -> Consent:
    """sub의 동의를 기록한다. 현재 버전이 아니면 ConsentVersionMismatchError"""
    check_version(data)
    existing = crud.get_consent(session, sub, data.version)
    if existing is not None:
        return existing
    return crud.create_consent(session, Consent.model_validate(data, update={"sub": sub}))


def delete_consents(session: Session, subs: Iterable[str]) -> None:
    """subs의 동의 기록을 모두 지운다 (계정을 지울 때)"""
    crud.delete_consents(session, subs)
