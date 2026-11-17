"""
Meeting 답하는 방식(mode) E2E 테스트

mode는 생성 때 필수이고 PATCH로 바꿀 수 있다. 바꿔도 저장된 날짜와 참여자의 가능 시간은 그대로다.
방식의 규칙은 생성과 수정(저장된 값에 수정 내용을 합친 결과) 모두에서 검사한다.
- hourly: 기간은 7일 이하
- daily: 하루 범위는 하루 전체(00:00–00:00)
- weekly: 기간은 정확히 7일, 제외 날짜 없음, 하루 범위는 하루 전체
"""
from datetime import date, timedelta

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


# ============================================================
# 방식의 규칙
# ============================================================

WHOLE_DAY = {"start_time": "00:00:00", "end_time": "00:00:00"}


def _days(start: str, days: int) -> dict:
    """start부터 days일 기간"""
    return {"start_date": start, "end_date": (date.fromisoformat(start) + timedelta(days=days - 1)).isoformat()}


@pytest.mark.e2e
@pytest.mark.parametrize(
    "body",
    [
        {**MEETINGS["hourly"], **_days("2024-02-05", 7)},
        {**MEETINGS["hourly"], **_days("2024-02-05", 1)},
        {**MEETINGS["hourly"], **_days("2024-02-26", 7)},  # 윤년 2월 말을 넘는 7일
        {**MEETINGS["hourly"], **_days("2024-02-05", 7), **WHOLE_DAY},
        {**MEETINGS["hourly"], **_days("2024-02-05", 7), "excluded_dates": ["2024-02-07"]},
        {**MEETINGS["daily"], **_days("2024-02-05", 1)},
        {**MEETINGS["daily"], **_days("2024-02-05", 8)},
        {**MEETINGS["daily"], "start_date": "2024-02-05", "end_date": "2024-05-05"},
        {**MEETINGS["daily"], "excluded_dates": ["2024-02-10", "2024-02-11"]},
        {**MEETINGS["daily"], "time_slot_minutes": 30},
        {**MEETINGS["weekly"], **_days("2024-02-28", 7)},
        {**MEETINGS["weekly"], "time_slot_minutes": 60},
    ],
)
def test_mode_rules_accepted(e2e_client, body):
    response = e2e_client.post("/v1/meetings", json=body)

    assert response.status_code == 201, response.text


@pytest.mark.e2e
@pytest.mark.parametrize(
    "body",
    [
        {**MEETINGS["hourly"], **_days("2024-02-05", 8)},
        {**MEETINGS["hourly"], **_days("2024-02-26", 8)},
        {**MEETINGS["hourly"], "start_date": "2024-02-05", "end_date": "2024-05-05"},
        {**MEETINGS["hourly"], **_days("2024-02-05", 8), **WHOLE_DAY},
        {**MEETINGS["daily"], "start_time": "09:00:00", "end_time": "18:00:00", "time_slot_minutes": 30},
        {**MEETINGS["daily"], "start_time": "00:00:00", "end_time": "12:00:00", "time_slot_minutes": 30},
        {**MEETINGS["daily"], "start_time": "12:00:00", "end_time": "00:00:00", "time_slot_minutes": 30},
        {**MEETINGS["daily"], "start_time": "00:00:00", "end_time": "23:59:00", "time_slot_minutes": 30},
        {**MEETINGS["weekly"], **_days("2024-02-05", 6)},
        {**MEETINGS["weekly"], **_days("2024-02-05", 8)},
        {**MEETINGS["weekly"], **_days("2024-02-05", 1)},
        {**MEETINGS["weekly"], "excluded_dates": ["2024-02-07"]},
        {**MEETINGS["weekly"], "start_time": "09:00:00", "end_time": "18:00:00", "time_slot_minutes": 30},
        {**MEETINGS["weekly"], "start_time": "00:00:00", "end_time": "23:00:00", "time_slot_minutes": 60},
        {**MEETINGS["weekly"], "start_time": "01:00:00", "end_time": "00:00:00", "time_slot_minutes": 60},
    ],
)
def test_mode_rules_rejected(e2e_client, body):
    response = e2e_client.post("/v1/meetings", json=body)

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert [error["loc"] for error in detail] == [["body"]]
    assert body["mode"] in detail[0]["msg"]
    assert e2e_client.get("/v1/meetings").json() == []


@pytest.mark.e2e
@pytest.mark.parametrize(
    "mode, patch",
    [
        ("hourly", {"mode": "weekly"}),  # 5일, 09:00–18:00
        ("hourly", {"mode": "daily"}),  # 09:00–18:00
        ("hourly", {"end_date": "2024-02-12"}),  # 8일
        ("hourly", {"start_date": "2024-02-01"}),  # 9일
        ("daily", {"mode": "hourly"}),  # 30일
        ("daily", {"mode": "weekly"}),  # 30일
        ("daily", {"start_time": "09:00:00", "time_slot_minutes": 30}),
        ("daily", {"end_time": "18:00:00", "time_slot_minutes": 30}),
        ("weekly", {"excluded_dates": ["2024-02-07"]}),
        ("weekly", {"end_date": "2024-02-12"}),
        ("weekly", {"start_date": "2024-02-06"}),
        ("weekly", {"start_time": "09:00:00", "time_slot_minutes": 30}),
        ("weekly", {"mode": "weekly", "end_date": "2024-02-10"}),
    ],
)
def test_patch_breaking_mode_rules_is_422_and_keeps_stored(e2e_client, mode, patch):
    meeting = _create(e2e_client, MEETINGS[mode])

    response = e2e_client.patch(f"/v1/meetings/{meeting['id']}", json=patch)

    assert response.status_code == 422, response.text
    assert response.json()["error_type"] == "InvalidMeetingError"
    assert e2e_client.get(f"/v1/meetings/{meeting['id']}").json() == meeting


@pytest.mark.e2e
@pytest.mark.parametrize(
    "mode, patch",
    [
        ("hourly", {"mode": "daily", **WHOLE_DAY}),
        ("hourly", {"mode": "daily", **WHOLE_DAY, "end_date": "2024-05-05"}),
        ("hourly", {"mode": "weekly", **WHOLE_DAY, "end_date": "2024-02-11"}),
        ("hourly", {"end_date": "2024-02-11"}),  # 7일
        ("daily", {"mode": "hourly", "end_date": "2024-02-11", "start_time": "09:00:00", "end_time": "18:00:00",
                   "time_slot_minutes": 30}),
        ("daily", {"mode": "weekly", "end_date": "2024-02-11"}),
        ("weekly", {"mode": "daily", "end_date": "2024-03-05", "excluded_dates": ["2024-02-14"]}),
        ("weekly", {"mode": "hourly", "start_time": "09:00:00", "end_time": "18:00:00", "time_slot_minutes": 30}),
        ("weekly", {"start_date": "2024-02-12", "end_date": "2024-02-18"}),  # 다음 주 7일
    ],
)
def test_patch_keeping_mode_rules_is_applied(e2e_client, mode, patch):
    meeting_id = _create(e2e_client, MEETINGS[mode])["id"]

    response = e2e_client.patch(f"/v1/meetings/{meeting_id}", json=patch)

    assert response.status_code == 200, response.text
    stored = e2e_client.get(f"/v1/meetings/{meeting_id}").json()
    assert {key: stored[key] for key in patch} == patch
