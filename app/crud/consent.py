"""
Consent CRUD 함수

약관 동의 기록 데이터 접근 레이어. 판정과 버전 확인은 app/domain/consent/service.py에서 한다.
"""
from typing import Iterable

from sqlalchemy import delete
from sqlmodel import Session

from app.models.consent import Consent


def get_consent(session: Session, sub: str, version: str) -> Consent | None:
    return session.get(Consent, (sub, version))


def create_consent(session: Session, consent: Consent) -> Consent:
    session.add(consent)
    session.flush()
    session.refresh(consent)
    return consent


def delete_consents(session: Session, subs: Iterable[str]) -> None:
    """subs의 동의 기록을 모든 버전에 걸쳐 지운다 (commit 없음)"""
    subs = list(subs)
    if subs:
        session.execute(delete(Consent).where(Consent.sub.in_(subs)))
