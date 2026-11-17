"""
미팅의 게스트 허용(allow_guests) E2E 테스트

- 생성·수정·조회 DTO에 allow_guests가 있고 기본값은 false다
- true는 공개 범위가 public일 때만 받는다 (아니면 422 InvalidMeetingError, 미팅은 그대로)
- 켠 뒤 공개 범위를 바꿔도 값은 그대로다 (게스트의 접근은 호스트 상태가 정한다)
"""
import pytest

MEETING = {
    "title": "게스트 허용 미팅",
    "start_date": "2024-02-01",
    "end_date": "2024-02-07",
    "timezone": "UTC",
    "mode": "hourly",
    "available_days": [0, 2, 4],
    "start_time": "09:00:00",
    "end_time": "18:00:00",
    "time_slot_minutes": 30,
}


def _create(client, **fields) -> dict:
    response = client.post("/v1/meetings", json={**MEETING, **fields})
    assert response.status_code == 201, response.text
    return response.json()


def _set_level(client, meeting_id: str, level: str) -> None:
    body = {"level": level}
    if level == "allowed_emails":
        body["allowed_emails"] = ["a@example.com"]
    assert client.put(f"/v1/visibility/meeting/{meeting_id}", json=body).status_code == 200


@pytest.mark.e2e
def test_default_is_false_in_create_and_read(e2e_client):
    created = _create(e2e_client)

    assert created["allow_guests"] is False
    assert e2e_client.get(f"/v1/meetings/{created['id']}").json()["allow_guests"] is False
    assert e2e_client.get("/v1/meetings").json()[0]["allow_guests"] is False
    assert e2e_client.get(f"/v1/meetings/{created['id']}/result").json()["meeting"]["allow_guests"] is False


@pytest.mark.e2e
def test_create_with_true_is_422_and_creates_nothing(e2e_client):
    """새 미팅은 공개 범위 설정이 없다(private)"""
    response = e2e_client.post("/v1/meetings", json={**MEETING, "allow_guests": True})

    assert response.status_code == 422
    assert response.json()["error_type"] == "InvalidMeetingError"
    assert e2e_client.get("/v1/meetings").json() == []


@pytest.mark.e2e
def test_create_with_false_is_accepted(e2e_client):
    assert _create(e2e_client, allow_guests=False)["allow_guests"] is False


@pytest.mark.e2e
def test_turn_on_while_public(e2e_client):
    meeting_id = _create(e2e_client)["id"]
    _set_level(e2e_client, meeting_id, "public")

    response = e2e_client.patch(f"/v1/meetings/{meeting_id}", json={"allow_guests": True})

    assert response.status_code == 200
    assert response.json()["allow_guests"] is True
    assert e2e_client.get(f"/v1/meetings/{meeting_id}").json()["allow_guests"] is True


@pytest.mark.e2e
@pytest.mark.parametrize("level", [None, "private", "friends", "allowed_emails"])
def test_turn_on_while_not_public_is_422_and_keeps_stored(e2e_client, level):
    meeting_id = _create(e2e_client)["id"]
    if level is not None:
        _set_level(e2e_client, meeting_id, level)

    response = e2e_client.patch(f"/v1/meetings/{meeting_id}", json={"allow_guests": True, "title": "바뀐 제목"})

    assert response.status_code == 422
    assert response.json()["error_type"] == "InvalidMeetingError"
    stored = e2e_client.get(f"/v1/meetings/{meeting_id}").json()
    assert stored["allow_guests"] is False
    assert stored["title"] == MEETING["title"]


@pytest.mark.e2e
def test_turn_off_is_accepted_at_any_level(e2e_client):
    meeting_id = _create(e2e_client)["id"]
    _set_level(e2e_client, meeting_id, "public")
    e2e_client.patch(f"/v1/meetings/{meeting_id}", json={"allow_guests": True})
    _set_level(e2e_client, meeting_id, "private")

    response = e2e_client.patch(f"/v1/meetings/{meeting_id}", json={"allow_guests": False})

    assert response.status_code == 200
    assert response.json()["allow_guests"] is False


@pytest.mark.e2e
def test_level_change_keeps_value_and_other_edits_still_work(e2e_client):
    """public에서 켠 뒤 private로 바꿔도 값은 남고, allow_guests를 보내지 않는 수정은 된다"""
    meeting_id = _create(e2e_client)["id"]
    _set_level(e2e_client, meeting_id, "public")
    e2e_client.patch(f"/v1/meetings/{meeting_id}", json={"allow_guests": True})
    _set_level(e2e_client, meeting_id, "private")

    response = e2e_client.patch(f"/v1/meetings/{meeting_id}", json={"title": "바뀐 제목"})

    assert response.status_code == 200
    assert response.json()["allow_guests"] is True
    assert response.json()["title"] == "바뀐 제목"


@pytest.mark.e2e
def test_sending_true_again_after_level_change_is_422(e2e_client):
    meeting_id = _create(e2e_client)["id"]
    _set_level(e2e_client, meeting_id, "public")
    e2e_client.patch(f"/v1/meetings/{meeting_id}", json={"allow_guests": True})
    _set_level(e2e_client, meeting_id, "private")

    response = e2e_client.patch(f"/v1/meetings/{meeting_id}", json={"allow_guests": True})

    assert response.status_code == 422


@pytest.mark.e2e
def test_null_is_422(e2e_client):
    meeting_id = _create(e2e_client)["id"]

    response = e2e_client.patch(f"/v1/meetings/{meeting_id}", json={"allow_guests": None})

    assert response.status_code == 422
    assert e2e_client.get(f"/v1/meetings/{meeting_id}").json()["allow_guests"] is False


@pytest.mark.e2e
def test_other_member_cannot_change_it(multi_user_e2e):
    owner = multi_user_e2e.as_user("owner")
    other = multi_user_e2e.as_user("other")
    meeting_id = _create(owner)["id"]
    _set_level(owner, meeting_id, "public")

    response = other.patch(f"/v1/meetings/{meeting_id}", json={"allow_guests": True})

    assert response.status_code == 404
    assert owner.get(f"/v1/meetings/{meeting_id}").json()["allow_guests"] is False
