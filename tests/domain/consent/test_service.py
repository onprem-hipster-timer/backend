"""약관 동의 기록 (app/domain/consent/service.py)

회원과 게스트가 같은 키(Kratos identity id, JWT sub)로 쓴다. (sub, version)마다 한 행이다.
선택 동의인 사용성 분석(analytics)은 같은 행에 두고, 같은 버전에 다시 보내면 그 값만 바꾼다.
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
from app.models.base import utc_now_naive
from app.models.consent import Consent

EARLIER = datetime(2026, 1, 1)
EARLIER_CHOICE = datetime(2026, 1, 2)


def _consent(version: str | None = None, **optional) -> ConsentCreate:
    return ConsentCreate(
        version=version or app_config.settings.CONSENT_VERSION, age_over_14=True, terms=True, privacy=True,
        **optional,
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


# ============ 사용성 분석 동의 (선택) ============

def _stored(session, sub: str, version: str | None = None) -> tuple:
    """DB에 있는 (analytics, analytics_updated_at, consented_at)"""
    session.expire_all()
    row = session.get(Consent, (sub, version or app_config.settings.CONSENT_VERSION))
    return row.analytics, row.analytics_updated_at, row.consented_at


def _age(session, sub: str, version: str | None = None) -> None:
    """저장된 시각을 앞당긴다 (시각이 바뀌었는지 가리려고). 고르지 않았으면 analytics_updated_at은 그대로 둔다"""
    row = session.get(Consent, (sub, version or app_config.settings.CONSENT_VERSION))
    row.consented_at = EARLIER
    if row.analytics_updated_at is not None:
        row.analytics_updated_at = EARLIER_CHOICE
    session.flush()


@pytest.mark.parametrize("optional", [{}, {"analytics": None}], ids=["omitted", "null"])
def test_analytics_is_not_chosen_when_omitted_or_null(test_session, optional):
    service.record_consent(test_session, "chose", _consent(analytics=True))

    service.record_consent(test_session, "a", _consent(**optional))

    assert _stored(test_session, "a")[:2] == (None, None)
    assert _stored(test_session, "chose")[0] is True


@pytest.mark.parametrize("value", [True, False])
def test_first_consent_stores_analytics_and_its_time(test_session, value):
    before = utc_now_naive()

    service.record_consent(test_session, "a", _consent(analytics=value))

    analytics, chosen_at, _ = _stored(test_session, "a")
    assert analytics is value
    assert chosen_at >= before


@pytest.mark.parametrize("first, second", [(True, False), (False, True), (None, True), (None, False)])
def test_same_version_again_changes_only_analytics_and_its_time(test_session, first, second):
    service.record_consent(test_session, "a", _consent(analytics=first))
    _age(test_session, "a")
    before = utc_now_naive()

    service.record_consent(test_session, "a", _consent(analytics=second))

    analytics, chosen_at, consented_at = _stored(test_session, "a")
    assert analytics is second
    assert chosen_at >= before
    assert consented_at == EARLIER
    assert _rows(test_session) == {("a", app_config.settings.CONSENT_VERSION)}


@pytest.mark.parametrize("stored", [True, False])
@pytest.mark.parametrize("optional", [{}, {"analytics": None}], ids=["omitted", "null"])
def test_same_version_again_without_analytics_keeps_stored_value_and_time(test_session, stored, optional):
    service.record_consent(test_session, "a", _consent(analytics=stored))
    _age(test_session, "a")

    service.record_consent(test_session, "a", _consent(**optional))

    assert _stored(test_session, "a") == (stored, EARLIER_CHOICE, EARLIER)


@pytest.mark.parametrize("value", [True, False])
def test_same_value_again_keeps_time(test_session, value):
    service.record_consent(test_session, "a", _consent(analytics=value))
    _age(test_session, "a")

    service.record_consent(test_session, "a", _consent(analytics=value))

    assert _stored(test_session, "a") == (value, EARLIER_CHOICE, EARLIER)


def test_other_version_is_refused_and_keeps_stored_analytics(test_session):
    service.record_consent(test_session, "a", _consent(analytics=True))
    _age(test_session, "a")

    with pytest.raises(ConsentVersionMismatchError):
        service.record_consent(test_session, "a", _consent("2000-01-01", analytics=False))

    assert _stored(test_session, "a") == (True, EARLIER_CHOICE, EARLIER)
    assert _rows(test_session) == {("a", app_config.settings.CONSENT_VERSION)}


@pytest.mark.parametrize("sent", [None, False, True])
def test_new_version_starts_from_what_its_consent_sent(test_session, monkeypatch, sent):
    old = app_config.settings.CONSENT_VERSION
    service.record_consent(test_session, "a", _consent(analytics=True))
    _age(test_session, "a")
    monkeypatch.setattr(app_config.settings, "CONSENT_VERSION", "2099-01-01")

    service.record_consent(test_session, "a", _consent(analytics=sent))

    analytics, chosen_at, _ = _stored(test_session, "a")
    assert analytics is sent
    assert (chosen_at is None) is (sent is None)
    assert _stored(test_session, "a", old) == (True, EARLIER_CHOICE, EARLIER)


def test_analytics_of_other_subs_is_untouched(test_session):
    service.record_consent(test_session, "a", _consent(analytics=True))
    service.record_consent(test_session, "b", _consent(analytics=True))
    service.record_consent(test_session, "c", _consent())
    _age(test_session, "b")

    service.record_consent(test_session, "a", _consent(analytics=False))

    assert _stored(test_session, "b") == (True, EARLIER_CHOICE, EARLIER)
    assert _stored(test_session, "c")[:2] == (None, None)


@pytest.mark.parametrize("theirs, mine, expected", [(True, False, False), (None, True, True), (True, None, True)])
def test_analytics_applies_to_row_another_request_recorded_first(test_session, monkeypatch, theirs, mine, expected):
    """다른 요청이 먼저 기록한 행은 처음 동의 시각을 두고, 보낸 analytics가 있으면 그 값이 마지막 값이다"""
    from app.crud import consent as crud

    version = app_config.settings.CONSENT_VERSION
    test_session.execute(insert(Consent).values(
        sub="a", version=version, consented_at=EARLIER,
        analytics=theirs, analytics_updated_at=None if theirs is None else EARLIER_CHOICE,
    ))
    real, calls = crud.get_consent, []

    def not_seen_yet(session, sub, version):
        """첫 조회 때는 다른 요청의 행이 아직 보이지 않는다"""
        calls.append(sub)
        return None if len(calls) == 1 else real(session, sub, version)

    monkeypatch.setattr(crud, "get_consent", not_seen_yet)

    service.record_consent(test_session, "a", _consent(analytics=mine))

    analytics, chosen_at, consented_at = _stored(test_session, "a")
    assert analytics is expected
    assert consented_at == EARLIER
    assert (chosen_at == EARLIER_CHOICE) is (mine is None)
    assert _rows(test_session) == {("a", version)}


@pytest.mark.parametrize("value", ["true", "yes", 1, 0, "", [True], {}])
def test_analytics_accepts_only_true_false_or_null(value):
    with pytest.raises(ValidationError):
        ConsentCreate.model_validate({"version": "v", "age_over_14": True, "terms": True, "privacy": True,
                                      "analytics": value})
