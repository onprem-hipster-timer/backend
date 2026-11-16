"""약관 동의 기록 (app/domain/consent/service.py)

회원과 게스트가 같은 키(Kratos identity id, JWT sub)로 쓴다. (sub, version)마다 한 행이다.
"""
from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import insert
from sqlmodel import select

import app.core.config as app_config
from app.domain.consent import service
from app.domain.consent.exceptions import ConsentVersionMismatchError
from app.domain.consent.schema.dto import ConsentCreate
from app.models.consent import Consent


def _consent(version: str | None = None) -> ConsentCreate:
    return ConsentCreate(
        version=version or app_config.settings.CONSENT_VERSION, age_over_14=True, terms=True, privacy=True
    )


def _rows(session) -> set[tuple[str, str]]:
    return {(c.sub, c.version) for c in session.exec(select(Consent)).all()}


def test_sub_without_consent_is_pending(test_session):
    assert service.consent_pending(test_session, "a") is True


def test_record_clears_pending(test_session):
    service.record_consent(test_session, "a", _consent())

    assert service.consent_pending(test_session, "a") is False
    assert _rows(test_session) == {("a", app_config.settings.CONSENT_VERSION)}


def test_other_version_is_refused_and_records_nothing(test_session):
    with pytest.raises(ConsentVersionMismatchError):
        service.record_consent(test_session, "a", _consent("2000-01-01"))

    assert _rows(test_session) == set()
    assert service.consent_pending(test_session, "a") is True


def test_check_version_refuses_only_other_versions():
    service.check_version(_consent())
    with pytest.raises(ConsentVersionMismatchError):
        service.check_version(_consent("2000-01-01"))


def test_recording_same_version_twice_keeps_one_row_with_first_time(test_session):
    first = service.record_consent(test_session, "a", _consent())
    first_at = first.consented_at
    first.consented_at = first_at - timedelta(days=1)
    test_session.flush()

    again = service.record_consent(test_session, "a", _consent())

    assert _rows(test_session) == {("a", app_config.settings.CONSENT_VERSION)}
    assert again.consented_at == first_at - timedelta(days=1)


def test_record_keeps_row_that_another_request_recorded_first(test_session, monkeypatch):
    from app.crud import consent as crud

    version = app_config.settings.CONSENT_VERSION
    earlier = datetime(2026, 1, 1)
    test_session.execute(insert(Consent).values(sub="a", version=version, consented_at=earlier))
    real, calls = crud.get_consent, []

    def not_seen_yet(session, sub, version):
        """첫 조회 때는 다른 요청의 행이 아직 보이지 않는다"""
        calls.append(sub)
        return None if len(calls) == 1 else real(session, sub, version)

    monkeypatch.setattr(crud, "get_consent", not_seen_yet)

    recorded = service.record_consent(test_session, "a", _consent())

    assert recorded.consented_at == earlier
    assert _rows(test_session) == {("a", version)}


def test_new_version_is_pending_again_and_earlier_rows_stay(test_session, monkeypatch):
    service.record_consent(test_session, "a", _consent())
    old = app_config.settings.CONSENT_VERSION
    monkeypatch.setattr(app_config.settings, "CONSENT_VERSION", "2099-01-01")

    assert service.consent_pending(test_session, "a") is True
    service.record_consent(test_session, "a", _consent())

    assert service.consent_pending(test_session, "a") is False
    assert _rows(test_session) == {("a", old), ("a", "2099-01-01")}


def test_each_sub_is_separate(test_session):
    service.record_consent(test_session, "member", _consent())

    assert service.consent_pending(test_session, "member") is False
    assert service.consent_pending(test_session, "guest") is True


def test_delete_removes_every_version_of_given_subs_only(test_session, monkeypatch):
    old = app_config.settings.CONSENT_VERSION
    for sub in ("a", "b", "c"):
        service.record_consent(test_session, sub, _consent())
    monkeypatch.setattr(app_config.settings, "CONSENT_VERSION", "2099-01-01")
    service.record_consent(test_session, "a", _consent())

    service.delete_consents(test_session, ["a", "b"])

    assert _rows(test_session) == {("c", old)}


def test_delete_without_subs_or_rows_does_nothing(test_session):
    service.record_consent(test_session, "a", _consent())

    service.delete_consents(test_session, [])
    service.delete_consents(test_session, ["nobody"])

    assert {s for s, _ in _rows(test_session)} == {"a"}


@pytest.mark.parametrize("item", ["age_over_14", "terms", "privacy"])
def test_every_item_must_be_true(item):
    body = {"version": "v", "age_over_14": True, "terms": True, "privacy": True}
    with pytest.raises(ValidationError):
        ConsentCreate(**{**body, item: False})
    del body[item]
    with pytest.raises(ValidationError):
        ConsentCreate(**body)
