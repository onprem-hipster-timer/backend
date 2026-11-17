"""회원의 사용성 분석 동의(PUT /v1/users/me/analytics-consent)는 회원 토큰만 받는다

게스트 토큰은 403, 토큰 없는 요청은 401로 GET /v1/users/me와 같다.
"""
import uuid

import pytest

from app.db.session import _session_manager
from app.domain.guest.host import GuestHostStatus
from app.models.user_profile import UserProfile
from tests.domain.guest.helpers import make_guest

ANALYTICS = "/v1/users/me/analytics-consent"
BODY = {"analytics_consent": "granted"}


@pytest.fixture
def guest(guest_client, host, kratos):
    resource_id = uuid.uuid4()
    host.statuses[resource_id] = GuestHostStatus.OPEN
    return make_guest(kratos, resource_id)


def _profile(sub: str) -> UserProfile | None:
    with _session_manager.get_session() as session:
        return session.get(UserProfile, sub)


def test_guest_token_gets_same_refusal_as_profile_read(guest_client, tokens, guest):
    headers = tokens.guest(guest.identity_id)

    put = guest_client.put(ANALYTICS, headers=headers, json=BODY)
    read = guest_client.get("/v1/users/me", headers=headers)

    assert put.status_code == read.status_code == 403
    assert put.json() == read.json()
    assert _profile(guest.identity_id) is None


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer not-a-token"}], ids=["no_token", "bad_token"])
def test_request_without_member_token_gets_same_refusal_as_profile_read(guest_client, headers):
    put = guest_client.put(ANALYTICS, headers=headers, json=BODY)
    read = guest_client.get("/v1/users/me", headers=headers)

    assert put.status_code == read.status_code == 401


def test_member_token_sets_own_choice(guest_client, tokens):
    r = guest_client.put(ANALYTICS, headers=tokens.member("member-1"), json=BODY)

    assert r.status_code == 200, r.text
    assert r.json()["id"] == "member-1"
    assert r.json()["analytics_consent"] == "granted"
    assert guest_client.get("/v1/users/me", headers=tokens.member("member-2")).json()["analytics_consent"] is None
