"""게스트 생성의 Cloudflare Turnstile 확인 (app/core/turnstile.py, app/middleware/guest_gate.py, POST /v1/guests)

토큰은 X-Turnstile-Token 헤더로 받는다.
"""
import uuid
from urllib.parse import parse_qs

import pytest

from app.domain.guest.host import GuestHostStatus
from tests.domain.guest.fakes import TURNSTILE_SECRET, TURNSTILE_VERIFY
from tests.domain.guest.helpers import guest_rows, make_guest

CREATE = "/v1/guests"
LOOKUP = "/v1/guests/lookup"
TOKEN_HEADER = "X-Turnstile-Token"


@pytest.fixture
def resource(host):
    resource_id = uuid.uuid4()
    host.statuses[resource_id] = GuestHostStatus.OPEN
    return resource_id


def _body(resource, name="민수", **changes) -> dict:
    body = {"resource_type": "meeting", "resource_id": str(resource), "name": name, "password": "1234"}
    return {**body, **changes}


def _create(client, body, token="token-from-widget", **kwargs):
    headers = {TOKEN_HEADER: token} if token is not None else {}
    return client.post(CREATE, json=body, headers={**headers, **kwargs.pop("headers", {})}, **kwargs)


def test_passed_token_creates_guest(guest_client, kratos, turnstile, resource):
    r = _create(guest_client, _body(resource))
    assert r.status_code == 201
    assert len(guest_rows()) == 1
    assert len(turnstile.requests) == 1


def test_secret_and_token_are_sent_as_form_fields_without_client_address(guest_client, turnstile, resource):
    _create(guest_client, _body(resource), headers={"CF-Connecting-IP": "203.0.113.7"})

    [request] = turnstile.requests
    assert str(request.url) == TURNSTILE_VERIFY
    assert request.method == "POST"
    assert request.headers["content-type"] == "application/x-www-form-urlencoded"
    fields = parse_qs(request.content.decode())
    assert fields == {"secret": [TURNSTILE_SECRET], "response": ["token-from-widget"]}
    assert b"203.0.113.7" not in request.content
    assert b"testclient" not in request.content


@pytest.mark.parametrize("token", [None, "", "a" * 2049], ids=["missing", "empty", "too_long"])
def test_missing_empty_or_long_token_is_403(guest_client, kratos, turnstile, resource, token):
    r = _create(guest_client, _body(resource), token=token)

    assert r.status_code == 403
    assert r.json()["error_type"] == "GuestVerificationFailedError"
    assert r.json()["message"] == "확인을 통과하지 못했습니다. 다시 시도하세요"
    assert r.json()["path"] == CREATE
    assert turnstile.requests == []
    assert kratos.identities == {}


def test_token_in_body_is_not_read(guest_client, kratos, turnstile, resource):
    r = _create(guest_client, _body(resource, turnstile_token="token-from-widget"), token=None)
    assert r.status_code == 403
    assert turnstile.requests == []


def test_token_of_max_length_is_accepted(guest_client, resource):
    assert _create(guest_client, _body(resource), token="a" * 2048).status_code == 201


def test_rejected_token_is_403_and_creates_nothing(guest_client, kratos, turnstile, resource):
    turnstile.success = False

    r = _create(guest_client, _body(resource))

    assert r.status_code == 403
    assert r.json()["error_type"] == "GuestVerificationFailedError"
    assert guest_rows() == []
    assert kratos.identities == {}


@pytest.mark.parametrize(
    "failure",
    ["down", "status_500", "not_json", "no_success", "success_not_bool"],
)
def test_unverifiable_token_is_503_and_creates_nothing(guest_client, kratos, turnstile, resource, failure):
    if failure == "down":
        turnstile.down = True
    elif failure == "status_500":
        turnstile.status = 500
    elif failure == "not_json":
        turnstile.body = b"<html>"
    elif failure == "no_success":
        turnstile.body = b'{"error-codes": []}'
    else:
        turnstile.body = b'{"success": "true"}'

    r = _create(guest_client, _body(resource))

    assert r.status_code == 503
    assert r.json()["error_type"] == "GuestServiceUnavailableError"
    assert guest_rows() == []
    assert kratos.identities == {}


def test_verification_comes_before_resource_and_name_checks(guest_client, kratos, host, turnstile, resource):
    make_guest(kratos, resource, name="민수")
    closed = uuid.uuid4()
    host.statuses[closed] = GuestHostStatus.CLOSED
    turnstile.success = False

    for body in (_body(resource, name="민수"), _body(closed)):
        r = _create(guest_client, body)
        assert r.status_code == 403
        assert r.json()["error_type"] == "GuestVerificationFailedError"
    assert len(turnstile.requests) == 2


def test_closed_resource_and_taken_name_are_refused_after_verification(guest_client, kratos, host, turnstile, resource):
    make_guest(kratos, resource, name="민수")
    assert _create(guest_client, _body(resource, name="민수")).status_code == 409

    closed = uuid.uuid4()
    host.statuses[closed] = GuestHostStatus.CLOSED
    assert _create(guest_client, _body(closed)).json()["error_type"] == "GuestEntryRefusedError"

    assert len(turnstile.requests) == 2
    assert len(kratos.identities) == 1


def test_lookup_needs_no_token(guest_client, kratos, turnstile, resource):
    make_guest(kratos, resource, name="민수")
    body = {"resource_type": "meeting", "resource_id": str(resource), "name": "민수"}
    assert guest_client.post(LOOKUP, json=body).json()["handle"]
    assert turnstile.requests == []


def test_flag_off_is_404_without_verification(guest_client, guest_off, turnstile, resource):
    guest_off()
    assert _create(guest_client, _body(resource)).status_code == 404
    assert _create(guest_client, _body(resource), token=None).status_code == 404
    assert turnstile.requests == []
