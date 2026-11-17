"""게스트의 약관 동의 (app/domain/consent)

- 생성(POST /v1/guests)은 동의를 게스트 행과 함께 기록한다 (test_guest_api.py, test_lookup_create.py)
- PUT /v1/guests/me/consent: 게스트 토큰. 현재 버전 동의를 기록한다. Turnstile 토큰은 받지 않는다.
  선택 동의인 사용성 분석(analytics)은 회원과 같이 기록하고 바꾼다 (tests/domain/consent/test_service.py)
- CONSENT_ENFORCED면 현재 버전에 동의하지 않은 게스트는 PUT /v1/guests/me/consent, DELETE /v1/guests/me 밖의
  게스트 경로가 428. 동의는 sub마다 따로라 회원과 게스트가 서로의 동의로 통과하지 않는다
- 게스트를 폐기하면(자기 삭제, 리소스 단위 폐기) 동의 기록도 지운다

428은 테스트 전용 라우트로 확인한다 (게스트 경로 중 동의 없이 부를 수 없는 경로가 아직 없다).
"""
import uuid

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import app.core.config as app_config
from app.core.auth import CurrentUser
from app.core.error_handlers import register_exception_handlers
from app.db.session import _session_manager
from app.domain.consent import service as consent_service
from app.domain.consent.schema.dto import ConsentCreate
from app.domain.guest import service
from app.domain.guest.dependencies import get_current_guest, require_guest_access
from app.domain.guest.host import GuestHostStatus
from app.domain.guest.model import Guest
from app.models.visibility import ResourceType
from tests.domain.guest.helpers import consent_analytics, consent_body, consent_rows, guest_rows, make_guest

CREATE = "/v1/guests"
ME = "/v1/guests/me"
CONSENT = "/v1/guests/me/consent"
TOKEN = {"X-Turnstile-Token": "t"}


@pytest.fixture
def resource(host):
    resource_id = uuid.uuid4()
    host.statuses[resource_id] = GuestHostStatus.OPEN
    return resource_id


@pytest.fixture
def enforced(monkeypatch):
    monkeypatch.setattr(app_config.settings, "CONSENT_ENFORCED", True)


@pytest.fixture
def bump_version(monkeypatch):
    def bump():
        monkeypatch.setattr(app_config.settings, "CONSENT_VERSION", "2099-01-01")
    return bump


@pytest.fixture
def routes(guest_client):
    """게스트를 받는 테스트 전용 라우트"""
    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/test/meetings/{meeting_id}")
    async def meeting_for_guest(guest: Guest = Depends(require_guest_access(ResourceType.MEETING, "meeting_id"))):
        return {"guest_id": str(guest.id)}

    @test_app.get("/test/guest")
    async def any_guest(user: CurrentUser = Depends(get_current_guest)):
        return {"sub": user.sub}

    return TestClient(test_app)


def _agree(sub: str) -> None:
    """sub가 현재 약관 버전에 동의한 기록을 바로 남긴다"""
    with _session_manager.get_session() as session:
        consent_service.record_consent(session, sub, ConsentCreate(**consent_body()))
        session.commit()


def _put(client, headers, body=None):
    return client.put(CONSENT, json=consent_body() if body is None else body, headers=headers)


# ============ PUT /v1/guests/me/consent ============

def test_put_records_consent_without_turnstile_token(guest_client, kratos, tokens, turnstile, resource):
    guest = make_guest(kratos, resource)

    r = _put(guest_client, tokens.guest(guest.identity_id))

    assert r.status_code == 204, r.text
    assert consent_rows() == {(guest.identity_id, app_config.settings.CONSENT_VERSION)}
    assert turnstile.requests == []


def test_put_twice_keeps_one_row(guest_client, kratos, tokens, resource):
    guest = make_guest(kratos, resource)
    headers = tokens.guest(guest.identity_id)
    assert _put(guest_client, headers).status_code == 204
    assert _put(guest_client, headers).status_code == 204
    assert consent_rows() == {(guest.identity_id, app_config.settings.CONSENT_VERSION)}


def test_put_new_version_adds_row(guest_client, kratos, tokens, resource, bump_version):
    guest = make_guest(kratos, resource)
    headers = tokens.guest(guest.identity_id)
    first = app_config.settings.CONSENT_VERSION
    assert _put(guest_client, headers).status_code == 204
    bump_version()
    assert _put(guest_client, headers).status_code == 204
    assert consent_rows() == {(guest.identity_id, first), (guest.identity_id, "2099-01-01")}


def test_put_other_version_is_409(guest_client, kratos, tokens, resource):
    guest = make_guest(kratos, resource)

    r = _put(guest_client, tokens.guest(guest.identity_id), consent_body("2000-01-01"))

    assert r.status_code == 409
    assert r.json()["error_type"] == "ConsentVersionMismatchError"
    assert r.json()["message"] == "Consent version is not current"
    assert consent_rows() == set()


def test_put_records_and_changes_analytics(guest_client, kratos, tokens, resource):
    guest = make_guest(kratos, resource)
    headers = tokens.guest(guest.identity_id)
    body = consent_body()

    assert _put(guest_client, headers, {**body, "analytics": True}).status_code == 204
    assert consent_analytics() == {guest.identity_id: True}
    assert _put(guest_client, headers, {**body, "analytics": False}).status_code == 204
    assert consent_analytics() == {guest.identity_id: False}
    assert _put(guest_client, headers, body).status_code == 204
    assert _put(guest_client, headers, {**body, "analytics": None}).status_code == 204
    assert consent_analytics() == {guest.identity_id: False}


def test_put_with_non_boolean_analytics_is_422(guest_client, kratos, tokens, resource):
    guest = make_guest(kratos, resource)
    headers = tokens.guest(guest.identity_id)
    assert _put(guest_client, headers, {**consent_body(), "analytics": True}).status_code == 204

    assert _put(guest_client, headers, {**consent_body(), "analytics": "no"}).status_code == 422
    assert consent_analytics() == {guest.identity_id: True}


@pytest.mark.parametrize("item", ["age_over_14", "terms", "privacy"])
def test_put_with_item_false_or_missing_is_422(guest_client, kratos, tokens, resource, item):
    guest = make_guest(kratos, resource)
    headers = tokens.guest(guest.identity_id)
    body = consent_body()

    assert _put(guest_client, headers, {**body, item: False}).status_code == 422
    del body[item]
    assert _put(guest_client, headers, body).status_code == 422
    assert consent_rows() == set()


def test_put_needs_guest_token(guest_client, kratos, tokens, resource):
    make_guest(kratos, resource)
    assert _put(guest_client, {}).status_code == 401
    assert _put(guest_client, tokens.member()).status_code == 403
    assert consent_rows() == set()


@pytest.mark.asyncio
async def test_put_for_discarded_guest_is_403_and_records_nothing(guest_client, kratos, tokens, resource):
    guest = make_guest(kratos, resource)
    headers = tokens.guest(guest.identity_id)
    await service.discard_guest(guest.identity_id)

    r = _put(guest_client, headers)

    assert r.status_code == 403
    assert consent_rows() == set()


def test_put_is_404_when_guest_flag_is_off(guest_client, guest_off, kratos, tokens, resource):
    guest = make_guest(kratos, resource)
    guest_off()
    assert _put(guest_client, tokens.guest(guest.identity_id)).status_code == 404
    assert consent_rows() == set()


# ============ 428 ============

@pytest.mark.parametrize("path", ["meeting", "guest"])
def test_guest_without_current_consent_gets_428_until_it_agrees(
        routes, guest_client, kratos, tokens, resource, enforced, bump_version, path
):
    guest = make_guest(kratos, resource)
    headers = tokens.guest(guest.identity_id)
    url = f"/test/meetings/{resource}" if path == "meeting" else "/test/guest"
    _agree(guest.identity_id)
    assert routes.get(url, headers=headers).status_code == 200

    bump_version()
    r = routes.get(url, headers=headers)
    assert r.status_code == 428
    assert r.json()["error_type"] == "ConsentRequiredError"
    assert r.json()["message"] == "consent_required"

    assert _put(guest_client, headers).status_code == 204
    assert routes.get(url, headers=headers).status_code == 200


@pytest.mark.asyncio
async def test_discarded_guest_gets_403_on_resource_route(routes, kratos, tokens, resource, enforced):
    guest = make_guest(kratos, resource)
    headers = tokens.guest(guest.identity_id)
    _agree(guest.identity_id)
    await service.discard_guest(guest.identity_id)

    r = routes.get(f"/test/meetings/{resource}", headers=headers)

    assert r.status_code == 403
    assert r.json()["error_type"] == "GuestAccessDeniedError"


def test_consent_and_self_delete_are_allowed_without_consent(guest_client, kratos, tokens, resource, enforced):
    agreeing = make_guest(kratos, resource, name="동의")
    leaving = make_guest(kratos, resource, name="떠남")

    assert _put(guest_client, tokens.guest(agreeing.identity_id)).status_code == 204
    assert guest_client.delete(ME, headers={**tokens.guest(leaving.identity_id), **TOKEN}).status_code == 204
    assert [g.id for g in guest_rows()] == [agreeing.id]


def test_guest_without_consent_passes_when_not_enforced(routes, kratos, tokens, resource):
    guest = make_guest(kratos, resource)
    assert app_config.settings.CONSENT_ENFORCED is False
    assert routes.get(f"/test/meetings/{resource}", headers=tokens.guest(guest.identity_id)).status_code == 200


def test_member_and_guest_consents_are_separate(routes, guest_client, kratos, tokens, resource, enforced):
    guest = make_guest(kratos, resource)
    member = tokens.member("member-1")
    _agree(guest.identity_id)

    assert routes.get("/test/guest", headers=tokens.guest(guest.identity_id)).status_code == 200
    assert guest_client.get("/v1/todos", headers=member).status_code == 428

    version = guest_client.get("/v1/users/me", headers=member).json()["consent_version"]
    assert guest_client.put("/v1/users/me/consent", headers=member, json=consent_body(version)).status_code == 200
    assert guest_client.get("/v1/todos", headers=member).status_code == 200

    other = make_guest(kratos, resource, name="다른 게스트")
    assert routes.get("/test/guest", headers=tokens.guest(other.identity_id)).status_code == 428


# ============ 폐기 ============

def test_self_delete_removes_consent(guest_client, kratos, tokens, resource):
    guest_client.post(CREATE, headers=TOKEN, json={
        "resource_type": "meeting", "resource_id": str(resource), "name": "민수", "password": "1234",
        "consent": consent_body(),
    })
    [row] = guest_rows()
    assert consent_rows() == {(row.identity_id, app_config.settings.CONSENT_VERSION)}

    r = guest_client.delete(ME, headers={**tokens.guest(row.identity_id), **TOKEN})

    assert r.status_code == 204
    assert consent_rows() == set()


def test_self_delete_removes_analytics_with_consent(guest_client, kratos, tokens, resource):
    leaving = make_guest(kratos, resource, name="떠남")
    staying = make_guest(kratos, resource, name="남음")
    for guest in (leaving, staying):
        assert _put(guest_client, tokens.guest(guest.identity_id), {**consent_body(), "analytics": True}).status_code == 204

    r = guest_client.delete(ME, headers={**tokens.guest(leaving.identity_id), **TOKEN})

    assert r.status_code == 204
    assert consent_analytics() == {staying.identity_id: True}


@pytest.mark.asyncio
async def test_resource_discard_removes_consent_of_its_guests_only(kratos, host, guest_db, resource, bump_version):
    other = uuid.uuid4()
    host.statuses[other] = GuestHostStatus.OPEN
    first = make_guest(kratos, resource, name="a")
    second = make_guest(kratos, resource, name="b")
    elsewhere = make_guest(kratos, other, name="a")
    for sub in (first.identity_id, second.identity_id, elsewhere.identity_id, "member-1"):
        _agree(sub)
    bump_version()
    _agree(first.identity_id)

    assert await service.discard_resource_guests(ResourceType.MEETING, resource) == 2

    assert {sub for sub, _ in consent_rows()} == {elsewhere.identity_id, "member-1"}


@pytest.mark.asyncio
async def test_discard_removes_consent_even_without_guest_row(kratos, guest_db, resource):
    guest = make_guest(kratos, resource)
    _agree(guest.identity_id)
    await service.discard_guest(guest.identity_id)
    _agree(guest.identity_id)

    await service.discard_guest(guest.identity_id)

    assert consent_rows() == set()


@pytest.mark.parametrize("discard", ["guest", "resource"])
@pytest.mark.asyncio
async def test_failed_consent_deletion_keeps_guest_row(kratos, guest_db, resource, monkeypatch, discard):
    """동의 삭제와 게스트 행 삭제는 한 트랜잭션이다"""
    from app.crud import consent as consent_crud

    guest = make_guest(kratos, resource)
    _agree(guest.identity_id)

    def broken(session, subs):
        raise RuntimeError("db down")

    monkeypatch.setattr(consent_crud, "delete_consents", broken)
    with pytest.raises(RuntimeError):
        if discard == "guest":
            await service.discard_guest(guest.identity_id)
        else:
            await service.discard_resource_guests(ResourceType.MEETING, resource)

    assert [g.id for g in guest_rows()] == [guest.id]
    assert consent_rows() == {(guest.identity_id, app_config.settings.CONSENT_VERSION)}
    assert kratos.deleted == []
