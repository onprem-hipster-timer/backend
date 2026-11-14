"""게스트 엔드포인트 (POST /v1/guests/lookup, POST /v1/guests, DELETE /v1/guests/me)와 플래그"""
import uuid

import pytest

from app.domain.guest.host import GuestHostStatus
from tests.domain.guest.helpers import guest_rows, make_guest

CREATE = "/v1/guests"
LOOKUP = "/v1/guests/lookup"
ME = "/v1/guests/me"


@pytest.fixture
def resource(host):
    resource_id = uuid.uuid4()
    host.statuses[resource_id] = GuestHostStatus.OPEN
    return resource_id


def _body(resource, name="민수", password="1234", resource_type="meeting") -> dict:
    return {"resource_type": resource_type, "resource_id": str(resource), "name": name, "password": password}


def _lookup_body(resource, name="민수", resource_type="meeting") -> dict:
    return {"resource_type": resource_type, "resource_id": str(resource), "name": name}


def test_create_returns_handle_and_guest(guest_client, kratos, resource):
    r = guest_client.post(CREATE, json=_body(resource))

    assert r.status_code == 201, r.text
    [row] = guest_rows()
    assert r.json() == {
        "guest_id": str(row.id),
        "handle": kratos.identities[row.identity_id]["traits"]["handle"],
        "resource_type": "meeting",
        "resource_id": str(resource),
    }


def test_lookup_returns_handle_of_named_guest(guest_client, resource):
    created = guest_client.post(CREATE, json=_body(resource)).json()

    r = guest_client.post(LOOKUP, json=_lookup_body(resource))

    assert r.status_code == 200, r.text
    assert r.json() == {"handle": created["handle"]}


def test_lookup_without_guest_returns_null_handle(guest_client, resource):
    guest_client.post(CREATE, json=_body(resource, name="민수"))
    r = guest_client.post(LOOKUP, json=_lookup_body(resource, name="영희"))
    assert r.status_code == 200
    assert r.json() == {"handle": None}


def test_lookup_takes_no_password(guest_client, resource):
    r = guest_client.post(LOOKUP, json=_body(resource))
    assert r.status_code == 200


def test_endpoints_need_no_token(guest_client, resource):
    assert guest_client.post(CREATE, json=_body(resource)).status_code == 201
    assert guest_client.post(LOOKUP, json=_lookup_body(resource)).status_code == 200


def test_taken_name_is_409(guest_client, kratos, resource):
    guest_client.post(CREATE, json=_body(resource, password="1234"))
    r = guest_client.post(CREATE, json=_body(resource, password="5678"))

    assert r.status_code == 409
    assert len(guest_rows()) == 1
    assert len(kratos.identities) == 1


def test_same_name_in_two_resources_both_succeed(guest_client, host, resource):
    other = uuid.uuid4()
    host.statuses[other] = GuestHostStatus.OPEN
    first = guest_client.post(CREATE, json=_body(resource))
    second = guest_client.post(CREATE, json=_body(other))
    assert first.status_code == second.status_code == 201
    assert first.json()["handle"] != second.json()["handle"]


@pytest.mark.parametrize("path", [CREATE, LOOKUP])
def test_closed_resource_is_403(guest_client, host, path):
    resource = uuid.uuid4()
    host.statuses[resource] = GuestHostStatus.CLOSED
    assert guest_client.post(path, json=_body(resource)).status_code == 403


@pytest.mark.parametrize("path", [CREATE, LOOKUP])
@pytest.mark.parametrize("status", [GuestHostStatus.EXPIRED, GuestHostStatus.MISSING, None])
def test_unusable_resource_gives_same_refusal(guest_client, host, status, path):
    """없는 리소스와 기간이 끝난 리소스, 받지 않는 리소스는 같은 응답이다"""
    resource = uuid.uuid4()
    if status is not None:
        host.statuses[resource] = status
    closed = uuid.uuid4()
    host.statuses[closed] = GuestHostStatus.CLOSED

    r = guest_client.post(path, json=_body(resource))
    closed_r = guest_client.post(path, json=_body(closed))

    assert r.status_code == closed_r.status_code == 403
    assert r.json()["message"] == closed_r.json()["message"]


@pytest.mark.parametrize("path", [CREATE, LOOKUP])
def test_unregistered_resource_type_is_403(guest_client, path):
    assert guest_client.post(path, json=_body(uuid.uuid4(), resource_type="todo")).status_code == 403


@pytest.mark.parametrize("path", [CREATE, LOOKUP])
def test_kratos_down_is_503(guest_client, kratos, resource, path):
    make_guest(kratos, resource, name="다른 이름")
    kratos.down.add("admin")
    assert guest_client.post(path, json=_body(resource)).status_code == 503
    assert len(guest_rows()) == 1


@pytest.mark.parametrize("path", [CREATE, LOOKUP])
@pytest.mark.parametrize("name", ["", "   ", "a" * 51, "민\x07수", "\n"])
def test_invalid_name_is_422(guest_client, kratos, resource, name, path):
    assert guest_client.post(path, json=_body(resource, name=name)).status_code == 422
    assert kratos.identities == {}


@pytest.mark.parametrize("name", ["a", "a" * 50, "  민수  ", "김 민수", "🙂"])
def test_valid_names(guest_client, resource, name):
    assert guest_client.post(CREATE, json=_body(resource, name=name)).status_code == 201
    assert guest_client.post(LOOKUP, json=_lookup_body(resource, name=name)).json()["handle"] is not None


@pytest.mark.parametrize("password", ["", "가" * 25, "a" * 73])
def test_invalid_password_is_422(guest_client, kratos, resource, password):
    """비어 있거나 UTF-8로 72바이트를 넘는 비밀번호 (가 25자 = 75바이트)"""
    assert guest_client.post(CREATE, json=_body(resource, password=password)).status_code == 422
    assert kratos.identities == {}


@pytest.mark.parametrize("password", ["1", " ", "a" * 72, "가" * 24, "1234"])
def test_any_short_password_is_accepted(guest_client, kratos, resource, password):
    r = guest_client.post(CREATE, json=_body(resource, password=password))
    assert r.status_code == 201
    assert kratos.passwords[guest_rows()[0].identity_id] == password


@pytest.mark.parametrize("field", ["resource_type", "resource_id", "name", "password"])
def test_create_missing_field_is_422(guest_client, resource, field):
    body = _body(resource)
    del body[field]
    assert guest_client.post(CREATE, json=body).status_code == 422


@pytest.mark.parametrize("field", ["resource_type", "resource_id", "name"])
def test_lookup_missing_field_is_422(guest_client, resource, field):
    body = _lookup_body(resource)
    del body[field]
    assert guest_client.post(LOOKUP, json=body).status_code == 422


@pytest.mark.parametrize("path", [CREATE, LOOKUP])
def test_unknown_resource_type_is_422(guest_client, resource, path):
    assert guest_client.post(path, json=_body(resource, resource_type="planet")).status_code == 422


# ============ 자기 삭제 ============

def test_guest_deletes_itself(guest_client, kratos, tokens, resource, guest_events):
    guest = make_guest(kratos, resource)

    r = guest_client.delete(ME, headers=tokens.guest(guest.identity_id))

    assert r.status_code == 204
    assert guest_rows() == []
    assert kratos.deleted == [guest.identity_id]
    assert len(guest_events) == 1
    # 같은 JWT로 다시 불러도 행이 없으므로 아무것도 남지 않는다
    assert guest_client.delete(ME, headers=tokens.guest(guest.identity_id)).status_code == 204


def test_self_delete_needs_guest_token(guest_client, kratos, tokens, resource):
    guest = make_guest(kratos, resource)
    assert guest_client.delete(ME).status_code == 401
    assert guest_client.delete(ME, headers=tokens.member()).status_code == 403
    assert len(guest_rows()) == 1


def test_self_delete_of_closed_resource_guest_is_allowed(guest_client, kratos, host, tokens):
    resource = uuid.uuid4()
    host.statuses[resource] = GuestHostStatus.CLOSED
    guest = make_guest(kratos, resource)
    assert guest_client.delete(ME, headers=tokens.guest(guest.identity_id)).status_code == 204
    assert guest_rows() == []


# ============ 플래그 ============

def test_flag_off_endpoints_are_404(guest_client, guest_off, kratos, tokens, resource):
    guest = make_guest(kratos, resource)
    guest_off()

    assert guest_client.post(CREATE, json=_body(resource)).status_code == 404
    assert guest_client.post(CREATE, json={}).status_code == 404
    assert guest_client.post(LOOKUP, json=_lookup_body(resource)).status_code == 404
    assert guest_client.post(LOOKUP, json={}).status_code == 404
    assert guest_client.delete(ME, headers=tokens.guest(guest.identity_id)).status_code == 404
    assert len(guest_rows()) == 1


def test_flag_off_guest_token_is_refused_on_member_routes(guest_client, guest_off, tokens):
    guest_off()
    assert guest_client.get("/v1/users/me", headers=tokens.guest("g-1")).status_code == 403
    # 클레임이 없는 회원 토큰은 플래그가 꺼져 있으면 받는다
    legacy = tokens.make("member-2", None, email="m2@example.com", email_verified=True)
    assert guest_client.get("/v1/users/me", headers={"Authorization": f"Bearer {legacy}"}).status_code == 200


def test_flag_on_token_without_schema_id_is_401(guest_client, tokens):
    legacy = tokens.make("member-2", None, email="m2@example.com", email_verified=True)
    assert guest_client.get("/v1/users/me", headers={"Authorization": f"Bearer {legacy}"}).status_code == 401
    assert guest_client.get("/v1/users/me", headers=tokens.member()).status_code == 200


@pytest.mark.parametrize("schema_id", [["guest"], {"id": "guest"}, 0, 1, True, False, ""])
def test_token_with_non_text_schema_id_is_401(guest_client, tokens, schema_id):
    token = tokens.make("member-1", schema_id, email="m@example.com", email_verified=True)
    r = guest_client.get("/v1/todos", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


@pytest.mark.parametrize("schema_id", ["Guest", "GUEST", " guest", "guest "])
def test_schema_id_is_compared_exactly(guest_client, kratos, tokens, resource, schema_id):
    guest = make_guest(kratos, resource)
    token = tokens.make(guest.identity_id, schema_id)
    r = guest_client.delete(ME, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
    assert len(guest_rows()) == 1


def test_guest_token_is_refused_on_member_route(guest_client, kratos, tokens, resource):
    guest = make_guest(kratos, resource)
    r = guest_client.get("/v1/users/me", headers=tokens.guest(guest.identity_id))
    assert r.status_code == 403


# ============ 유니코드 정규화 (NFC) ============

def _nfd(text: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFD", text)


def test_nfc_and_nfd_name_are_one_name(guest_client, kratos, resource):
    assert _nfd("민수") != "민수"
    created = guest_client.post(CREATE, json=_body(resource, name="민수")).json()

    assert guest_client.post(CREATE, json=_body(resource, name=_nfd("민수"))).status_code == 409
    assert guest_client.post(LOOKUP, json=_lookup_body(resource, name=_nfd("민수"))).json() == {
        "handle": created["handle"]
    }
    assert len(guest_rows()) == 1


def test_nfd_name_is_stored_as_nfc(guest_client, kratos, resource):
    guest_client.post(CREATE, json=_body(resource, name=_nfd("민수")))
    assert kratos.name_of(guest_rows()[0].identity_id) == "민수"


def test_nfd_password_is_stored_as_nfc(guest_client, kratos, resource):
    guest_client.post(CREATE, json=_body(resource, password=_nfd("비밀")))
    assert kratos.passwords[guest_rows()[0].identity_id] == "비밀"


def test_name_length_is_measured_after_normalisation(guest_client, kratos, resource):
    name = "가" * 50
    assert len(_nfd(name)) > 50
    assert guest_client.post(CREATE, json=_body(resource, name=_nfd(name))).status_code == 201
    assert kratos.name_of(guest_rows()[0].identity_id) == name


def test_password_bytes_are_measured_after_normalisation(guest_client, kratos, resource):
    password = "가" * 24  # NFC 72바이트
    assert len(_nfd(password).encode()) > 72
    assert guest_client.post(CREATE, json=_body(resource, password=_nfd(password))).status_code == 201
    assert kratos.passwords[guest_rows()[0].identity_id] == password


# ============ 이름 정규형 ============

@pytest.mark.parametrize(
    "variant",
    ["민수\u200b", "\u200b민수", "민\u200d수", "민수\u2060", "민수\ufeff", "\u202e민수", "민\u00ad수",
     "민수\ue000", "민수\u0378", "민\x07수"],
    ids=["zwsp_end", "zwsp_start", "zwj", "word_joiner", "bom", "rlo", "soft_hyphen", "private_use",
         "unassigned", "bell"],
)
@pytest.mark.parametrize("path", [CREATE, LOOKUP])
def test_name_with_refused_character_is_422(guest_client, kratos, resource, variant, path):
    assert guest_client.post(path, json=_body(resource, name=variant)).status_code == 422
    assert kratos.identities == {}


@pytest.mark.parametrize("variant", ["김  민수", "김 민수", "김\u3000민수", "김\t민수", "김\u00a0민수", " 김 \u2003 민수\n"])
def test_whitespace_runs_are_one_space(guest_client, kratos, resource, variant):
    created = guest_client.post(CREATE, json=_body(resource, name="김 민수")).json()

    assert guest_client.post(CREATE, json=_body(resource, name=variant)).status_code == 409
    assert guest_client.post(LOOKUP, json=_lookup_body(resource, name=variant)).json() == {
        "handle": created["handle"]
    }


def test_name_is_stored_in_canonical_form(guest_client, kratos, resource):
    guest_client.post(CREATE, json=_body(resource, name=" 김\u3000\u3000민수 "))
    assert kratos.name_of(guest_rows()[0].identity_id) == "김 민수"


def test_line_and_paragraph_separators_count_as_whitespace(guest_client, kratos, resource):
    """Python에서 공백 문자인 U+2028·U+2029는 공백 하나로 바뀐다"""
    guest_client.post(CREATE, json=_body(resource, name="김\u2028민수\u2029"))
    assert kratos.name_of(guest_rows()[0].identity_id) == "김 민수"


def test_name_length_is_measured_after_collapsing_whitespace(guest_client, resource):
    name = "가 " * 25 + "      "  # 공백을 줄이면 49자
    assert guest_client.post(CREATE, json=_body(resource, name=name)).status_code == 201
    assert guest_client.post(CREATE, json=_body(resource, name="가" * 51)).status_code == 422


@pytest.mark.parametrize("name", ["🙂", "👍🏽", "🇰🇷", "민수🙂"])
def test_emoji_without_joiner_is_accepted(guest_client, resource, name):
    assert guest_client.post(CREATE, json=_body(resource, name=name)).status_code == 201


def test_emoji_sequence_with_zero_width_joiner_is_refused(guest_client, kratos, resource):
    family = "👨\u200d👩\u200d👧"
    assert guest_client.post(CREATE, json=_body(resource, name=family)).status_code == 422
    assert kratos.identities == {}


def test_stored_name_in_other_spacing_is_taken(guest_client, kratos, resource):
    """Kratos에 정규형이 아닌 이름이 저장돼 있어도 정규형으로 비교한다"""
    stored = make_guest(kratos, resource, name="김\u3000 민수")
    assert guest_client.post(CREATE, json=_body(resource, name="김 민수")).status_code == 409
    found = guest_client.post(LOOKUP, json=_lookup_body(resource, name="김 민수")).json()["handle"]
    assert found == kratos.identities[stored.identity_id]["traits"]["handle"]


def test_stored_name_without_canonical_form_never_matches(guest_client, kratos, resource):
    make_guest(kratos, resource, name="민수\u200b")
    assert guest_client.post(LOOKUP, json=_lookup_body(resource, name="민수")).json() == {"handle": None}
    assert guest_client.post(CREATE, json=_body(resource, name="민수")).status_code == 201


def test_lookup_of_closed_resource_returns_no_handle(guest_client, host, resource):
    assert guest_client.post(CREATE, json=_body(resource)).status_code == 201
    host.statuses[resource] = GuestHostStatus.CLOSED
    r = guest_client.post(LOOKUP, json=_lookup_body(resource))
    assert r.status_code == 403
    assert "handle" not in r.text
