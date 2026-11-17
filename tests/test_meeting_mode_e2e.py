"""
Meeting 답하는 방식(mode) E2E 테스트

mode는 생성 때 필수이고 PATCH로 바꿀 수 있다. 바꿔도 저장된 날짜와 참여자의 가능 시간은 그대로다.
방식의 규칙은 생성과 수정(저장된 값에 수정 내용을 합친 결과) 모두에서 검사한다.
수정은 규칙이 읽는 필드(MODE_RULE_FIELDS) 중 하나라도 저장된 값과 달라질 때만 규칙을 본다.
- hourly: 기간은 7일 이하
- daily: 하루 범위는 하루 전체(00:00–00:00)
- weekly: 기간은 정확히 7일, 제외 날짜 없음, 하루 범위는 하루 전체
"""
from datetime import date, time, timedelta

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


# ============================================================
# 방식의 규칙을 어기는 저장된 미팅 (규칙이 생기기 전의 행)
# ============================================================

# (저장된 행, 규칙 필드를 바꾸지만 여전히 어기는 수정, 규칙을 지키게 하는 수정)
LEGACY_MEETINGS = {
    "hourly_longer_than_7_days": (
        {"mode": "hourly", **_days("2024-02-05", 10), "start_time": "09:00:00", "end_time": "18:00:00",
         "time_slot_minutes": 30},
        {"end_date": "2024-02-13"},  # 9일
        {"end_date": "2024-02-11"},  # 7일
    ),
    "daily_not_whole_day": (
        {"mode": "daily", "start_date": "2024-02-05", "end_date": "2024-03-05", "start_time": "09:00:00",
         "end_time": "18:00:00", "time_slot_minutes": 30},
        {"start_time": "10:00:00"},
        WHOLE_DAY,
    ),
    "weekly_not_whole_day": (
        {"mode": "weekly", **_days("2024-02-05", 7), "start_time": "09:00:00", "end_time": "18:00:00",
         "time_slot_minutes": 30},
        {"end_time": "17:00:00"},
        WHOLE_DAY,
    ),
    "weekly_not_7_days": (
        {"mode": "weekly", **_days("2024-02-05", 10), **WHOLE_DAY, "time_slot_minutes": 1440},
        {"end_date": "2024-02-12"},  # 8일
        {"end_date": "2024-02-11"},  # 7일
    ),
    "weekly_with_excluded_dates": (
        {"mode": "weekly", **_days("2024-02-05", 7), **WHOLE_DAY, "time_slot_minutes": 1440,
         "excluded_dates": ["2024-02-07"]},
        {"excluded_dates": ["2024-02-08"]},
        {"excluded_dates": []},
    ),
}


def _insert(row: dict) -> str:
    """API를 거치지 않고 mock 사용자(test-user-id)의 미팅 행을 넣는다"""
    from app.db.session import _session_manager
    from app.models.meeting import Meeting

    with _session_manager.get_session() as session:
        meeting = Meeting(
            owner_id="test-user-id",
            title="예전 미팅",
            timezone="UTC",
            start_date=date.fromisoformat(row["start_date"]),
            end_date=date.fromisoformat(row["end_date"]),
            excluded_dates=[date.fromisoformat(day) for day in row.get("excluded_dates", [])],
            mode=row["mode"],
            start_time=time.fromisoformat(row["start_time"]),
            end_time=time.fromisoformat(row["end_time"]),
            time_slot_minutes=row["time_slot_minutes"],
        )
        session.add(meeting)
        session.commit()
        return str(meeting.id)


@pytest.mark.e2e
@pytest.mark.parametrize("shape", LEGACY_MEETINGS)
def test_legacy_rows_break_mode_rules(e2e_client, shape):
    """기준: 이 행들은 생성으로는 만들 수 없다"""
    row, _, _ = LEGACY_MEETINGS[shape]

    response = e2e_client.post("/v1/meetings", json={"title": "예전 미팅", "timezone": "UTC", **row})

    assert response.status_code == 422, response.text
    assert row["mode"] in response.json()["detail"][0]["msg"]


@pytest.mark.e2e
@pytest.mark.parametrize("shape", LEGACY_MEETINGS)
@pytest.mark.parametrize(
    "patch",
    [
        {"title": "새 제목"},
        {"description": "설명"},
        {"description": None},
        {"timezone": "Asia/Seoul"},
        {"time_slot_minutes": 60},
        {"allow_guests": False},
        {"title": "새 제목", "start_date": None, "end_date": None, "start_time": None, "end_time": None},
    ],
)
def test_legacy_row_accepts_patch_without_rule_fields(e2e_client, shape, patch):
    row, _, _ = LEGACY_MEETINGS[shape]
    meeting_id = _insert(row)
    before = e2e_client.get(f"/v1/meetings/{meeting_id}").json()

    response = e2e_client.patch(f"/v1/meetings/{meeting_id}", json=patch)

    assert response.status_code == 200, response.text
    stored = e2e_client.get(f"/v1/meetings/{meeting_id}").json()
    sent = {key: value for key, value in patch.items() if value is not None or key == "description"}
    assert {key: stored[key] for key in sent} == sent
    unchanged = set(before) - set(sent) - {"updated_at"}
    assert {key: stored[key] for key in unchanged} == {key: before[key] for key in unchanged}


@pytest.mark.e2e
@pytest.mark.parametrize("shape", LEGACY_MEETINGS)
def test_legacy_row_accepts_rule_fields_sent_unchanged(e2e_client, shape):
    """화면이 폼 전체를 보내도 규칙 필드가 저장된 값과 같으면 바뀐 것이 아니다"""
    row, _, _ = LEGACY_MEETINGS[shape]
    meeting_id = _insert(row)
    before = e2e_client.get(f"/v1/meetings/{meeting_id}").json()
    body = {
        key: before[key]
        for key in ("mode", "start_date", "end_date", "excluded_dates", "start_time", "end_time")
    }

    response = e2e_client.patch(f"/v1/meetings/{meeting_id}", json={**body, "title": "새 제목"})

    assert response.status_code == 200, response.text
    assert response.json()["title"] == "새 제목"


@pytest.mark.e2e
@pytest.mark.parametrize("shape", LEGACY_MEETINGS)
def test_legacy_row_refuses_rule_field_change_that_still_breaks_rules(e2e_client, shape):
    row, still_breaking, _ = LEGACY_MEETINGS[shape]
    meeting_id = _insert(row)
    before = e2e_client.get(f"/v1/meetings/{meeting_id}").json()

    for patch in (still_breaking, {**still_breaking, "title": "새 제목"}):
        response = e2e_client.patch(f"/v1/meetings/{meeting_id}", json=patch)

        assert response.status_code == 422, response.text
        assert response.json()["error_type"] == "InvalidMeetingError"
        assert row["mode"] in response.json()["message"]
        assert e2e_client.get(f"/v1/meetings/{meeting_id}").json() == before


@pytest.mark.e2e
@pytest.mark.parametrize("shape", LEGACY_MEETINGS)
def test_legacy_row_accepts_patch_that_fixes_rules(e2e_client, shape):
    row, _, fixing = LEGACY_MEETINGS[shape]
    meeting_id = _insert(row)

    response = e2e_client.patch(f"/v1/meetings/{meeting_id}", json=fixing)

    assert response.status_code == 200, response.text
    stored = e2e_client.get(f"/v1/meetings/{meeting_id}").json()
    assert {key: stored[key] for key in fixing} == fixing
    # 이제 규칙을 지키므로 생성으로도 같은 미팅을 만들 수 있다
    fields = ("mode", "start_date", "end_date", "excluded_dates", "start_time", "end_time", "time_slot_minutes")
    body = {"title": "같은 모양", "timezone": "UTC", **{key: stored[key] for key in fields}}
    assert e2e_client.post("/v1/meetings", json=body).status_code == 201


@pytest.mark.e2e
@pytest.mark.parametrize(
    "shape, patch",
    [
        ("daily_not_whole_day", {"time_slot_minutes": 600}),  # 하루 범위 9시간보다 크다
        ("weekly_not_whole_day", {"title": "새 제목", "time_slot_minutes": 1440}),
        ("hourly_longer_than_7_days", {"title": "   "}),
        ("weekly_with_excluded_dates", {"description": "x" * 2001}),
    ],
)
def test_legacy_row_still_checks_other_rules(e2e_client, shape, patch):
    row, _, _ = LEGACY_MEETINGS[shape]
    meeting_id = _insert(row)
    before = e2e_client.get(f"/v1/meetings/{meeting_id}").json()

    response = e2e_client.patch(f"/v1/meetings/{meeting_id}", json=patch)

    assert response.status_code == 422, response.text
    assert e2e_client.get(f"/v1/meetings/{meeting_id}").json() == before
