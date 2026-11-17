"""
약관 동의 서비스

회원과 게스트가 함께 쓴다. 키는 Kratos identity id(JWT sub)이고, 현재 시행 중인 버전(settings.CONSENT_VERSION)에
동의한 행이 있으면 동의한 것이다. 버전마다 한 행을 남기고, 같은 버전에 다시 동의하면 처음 행을 그대로 둔다.
선택 동의인 사용성 분석(analytics)은 그 행에 두고, 같은 버전에 다시 동의하며 다른 값을 보내면 그 값과 시각만 바꾼다.

- 회원: 인증 의존성(app/core/auth/dependencies.py)과 GraphQL 컨텍스트의 428, PUT /v1/users/me/consent, 파기(app/domain/user/purge.py)
- 게스트: 생성(Kratos를 부르기 전에 버전을 확인하고, 동의를 게스트 행과 한 트랜잭션에 기록), 게스트 의존성의 428,
  PUT /v1/guests/me/consent, 폐기(게스트 행 삭제와 한 트랜잭션) (app/domain/guest)

함수는 받은 세션에 쓰고 커밋하지 않는다.

테스트: tests/domain/consent/test_service.py
"""
from typing import Iterable

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

import app.core.config as app_config
from app.crud import consent as crud
from app.domain.consent.exceptions import ConsentVersionMismatchError
from app.domain.consent.model import Consent
from app.domain.consent.schema.dto import ConsentCreate
from app.models.base import utc_now_naive


def check_version(data: ConsentCreate) -> None:
    """현재 약관 버전이 아니면 ConsentVersionMismatchError"""
    if data.version != app_config.settings.CONSENT_VERSION:
        raise ConsentVersionMismatchError()


def current_consent(session: Session, sub: str) -> Consent | None:
    """sub가 현재 약관 버전에 동의한 행. 동의하지 않았으면 None"""
    return crud.get_consent(session, sub, app_config.settings.CONSENT_VERSION)


def consent_pending(session: Session, sub: str) -> bool:
    """sub가 현재 약관 버전에 동의하지 않았으면 True"""
    return current_consent(session, sub) is None


def record_consent(session: Session, sub: str, data: ConsentCreate) -> Consent:
    """sub의 동의를 기록한다. 현재 버전이 아니면 ConsentVersionMismatchError.

    이미 기록한 버전이면 처음 행(consented_at)을 두고, analytics를 보냈고 저장된 값과 다르면 analytics와
    analytics_updated_at만 바꾼다. analytics가 없거나(null) 같은 값이면 바꾸지 않는다.
    """
    check_version(data)
    existing = crud.get_consent(session, sub, data.version)
    if existing is not None:
        return _apply_analytics(session, existing, data)

    chosen_at = None if data.analytics is None else utc_now_naive()
    # 앞서 쌓인 변경은 SAVEPOINT 밖에서 먼저 flush해, 그 변경의 IntegrityError를 여기서 삼키지 않는다
    session.flush()
    try:
        with session.begin_nested():
            return crud.create_consent(
                session, Consent.model_validate(data, update={"sub": sub, "analytics_updated_at": chosen_at})
            )
    except IntegrityError:
        # 같은 동의를 다른 요청이 먼저 기록했다. 그 행에 이 요청의 analytics를 적용한다
        existing = crud.get_consent(session, sub, data.version)
        if existing is None:
            raise
        return _apply_analytics(session, existing, data)


def _apply_analytics(session: Session, consent: Consent, data: ConsentCreate) -> Consent:
    """이미 있는 동의 행에 보낸 analytics를 적용한다. 없거나(null) 저장된 값과 같으면 바꾸지 않는다"""
    if data.analytics is None:
        return consent
    return crud.set_analytics(session, consent, data.analytics, utc_now_naive())


def delete_consents(session: Session, subs: Iterable[str]) -> None:
    """subs의 동의 기록을 모두 지운다 (계정을 지울 때)"""
    crud.delete_consents(session, subs)
