"""
Consent CRUD 함수

약관 동의 기록 데이터 접근 레이어. 판정과 버전 확인은 app/domain/consent/service.py에서 한다.
"""
from datetime import datetime
from typing import Iterable

from sqlalchemy import delete, update
from sqlmodel import Session

from app.models.consent import Consent


def get_consent(session: Session, sub: str, version: str) -> Consent | None:
    return session.get(Consent, (sub, version))


def create_consent(session: Session, consent: Consent) -> Consent:
    session.add(consent)
    session.flush()
    session.refresh(consent)
    return consent


def set_analytics(session: Session, consent: Consent, value: bool, at: datetime) -> Consent:
    """consent 행의 analytics가 value와 다를 때만 value와 바꾼 시각 at으로 바꾼다.

    비교와 변경을 한 UPDATE 문으로 해, 겹친 요청은 행 잠금 뒤의 값으로 다시 비교한다(마지막 값이 남는다).
    """
    session.execute(
        update(Consent)
        .where(
            Consent.sub == consent.sub,
            Consent.version == consent.version,
            Consent.analytics.is_distinct_from(value),
        )
        .values(analytics=value, analytics_updated_at=at)
        .execution_options(synchronize_session=False)
    )
    session.refresh(consent)
    return consent


def delete_consents(session: Session, subs: Iterable[str]) -> None:
    """subs의 동의 기록을 모든 버전에 걸쳐 지운다 (commit 없음)"""
    subs = list(subs)
    if subs:
        session.execute(delete(Consent).where(Consent.sub.in_(subs)))
