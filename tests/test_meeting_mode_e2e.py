"""
Meeting 답하는 방식(mode) E2E 테스트

mode는 생성 때 필수이고 PATCH로 바꿀 수 있다. 바꿔도 저장된 날짜와 참여자의 가능 시간은 그대로다.
"""
import pytest

# 방식마다 그 방식의 규칙을 지키는 미팅
MEETINGS = {
    "hourly": {
        "title": "시간 고르기",
        "start_date": "2024-02-05",  # 월요일
        "end_date": "2024-02-09",
        "timezone": "UTC",
        "mode": "hourly",
        "start_time": "09:00:00",
        "end_time": "18:00:00",
        "time_slot_minutes": 30,
    },
    "daily": {
        "title": "날짜 고르기",
        "start_date": "2024-02-05",
        "end_date": "2024-03-05",
        "timezone": "UTC",
        "mode": "daily",
        "start_time": "00:00:00",
        "end_time": "00:00:00",
        "time_slot_minutes": 1440,
    },
    "weekly": {
        "title": "요일 고르기",
        "start_date": "2024-02-05",
        "end_date": "2024-02-11",
        "timezone": "UTC",
        "mode": "weekly",
        "start_time": "00:00:00",
        "end_time": "00:00:00",
        "time_slot_minutes": 1440,
    },
}

_SHAPE_FIELDS = ("start_date", "end_date", "timezone", "start_time", "end_time", "time_slot_minutes")


def _create(client, body: dict) -> dict:
    response = client.post("/v1/meetings", json=body)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.e2e
@pytest.mark.parametrize("mode", ["hourly", "daily", "weekly"])
def test_mode_is_stored_and_returned(e2e_client, mode):
    created = _create(e2e_client, MEETINGS[mode])

    assert created["mode"] == mode
    assert e2e_client.get(f"/v1/meetings/{created['id']}").json()["mode"] == mode
    assert [m["mode"] for m in e2e_client.get("/v1/meetings").json()] == [mode]


@pytest.mark.e2e
def test_create_without_mode_is_422(e2e_client):
    body = {key: value for key, value in MEETINGS["hourly"].items() if key != "mode"}

    response = e2e_client.post("/v1/meetings", json=body)

    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["loc"] == ["body", "mode"]
    assert e2e_client.get("/v1/meetings").json() == []


@pytest.mark.e2e
@pytest.mark.parametrize("mode", ["monthly", "HOURLY", "Hourly", "", None, 0, ["hourly"]])
def test_create_with_unknown_mode_is_422(e2e_client, mode):
    response = e2e_client.post("/v1/meetings", json={**MEETINGS["hourly"], "mode": mode})

    assert response.status_code == 422, response.text
    assert e2e_client.get("/v1/meetings").json() == []


@pytest.mark.e2e
def test_patch_mode_keeps_dates_and_answers(e2e_client):
    # 하루 전체·7일 기간은 세 방식 모두 받는다
    meeting = _create(e2e_client, {**MEETINGS["weekly"], "mode": "hourly"})
    meeting_id = meeting["id"]
    participant_id = e2e_client.post(
        f"/v1/meetings/{meeting_id}/participate", json={"display_name": "참여자"},
    ).json()["id"]
    slots = [
        {"start_time": "2024-02-05T00:00:00Z", "end_time": "2024-02-06T00:00:00Z"},
        {"start_time": "2024-02-07T09:10:00Z", "end_time": "2024-02-07T10:20:00Z"},
    ]
    assert e2e_client.put(
        f"/v1/meetings/{meeting_id}/availability", params={"participant_id": participant_id}, json=slots,
    ).status_code == 200
    availability = e2e_client.get(f"/v1/meetings/{meeting_id}/availability").json()
    grid = e2e_client.get(f"/v1/meetings/{meeting_id}/result").json()["availability_grid"]

    for mode in ("daily", "weekly", "hourly"):
        response = e2e_client.patch(f"/v1/meetings/{meeting_id}", json={"mode": mode})

        assert response.status_code == 200, response.text
        assert response.json()["mode"] == mode
        stored = e2e_client.get(f"/v1/meetings/{meeting_id}").json()
        assert stored["mode"] == mode
        assert {k: stored[k] for k in _SHAPE_FIELDS} == {k: meeting[k] for k in _SHAPE_FIELDS}
        assert e2e_client.get(f"/v1/meetings/{meeting_id}/availability").json() == availability
        assert e2e_client.get(f"/v1/meetings/{meeting_id}/result").json()["availability_grid"] == grid


@pytest.mark.e2e
@pytest.mark.parametrize("mode", [None, "monthly", ""])
def test_patch_invalid_mode_is_422_and_keeps_stored(e2e_client, mode):
    meeting_id = _create(e2e_client, MEETINGS["hourly"])["id"]

    response = e2e_client.patch(f"/v1/meetings/{meeting_id}", json={"mode": mode})

    assert response.status_code == 422, response.text
    assert e2e_client.get(f"/v1/meetings/{meeting_id}").json()["mode"] == "hourly"


@pytest.mark.e2e
def test_patch_without_mode_keeps_mode(e2e_client):
    meeting_id = _create(e2e_client, MEETINGS["daily"])["id"]

    response = e2e_client.patch(f"/v1/meetings/{meeting_id}", json={"title": "새 제목"})

    assert response.status_code == 200, response.text
    assert response.json()["mode"] == "daily"
