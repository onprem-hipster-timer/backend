"""
Meeting 가능 시간의 unavailable 구간과 하루 범위 E2E 테스트

unavailable 구간을 보낸 답은 하루 범위를 available·unavailable 구간으로 빈틈없이 채워야 한다.
- hourly: 날마다 따로 본다. 그날 범위에 unavailable 구간이 있는 날만 채운다
- daily·weekly: 답 전체로 본다. 어느 미팅 날짜의 범위에든 unavailable 구간이 있으면 모든 미팅 날짜를 채운다
- available 구간만 있거나 구간이 없으면 어느 방식이든 받는다
- 미팅 날짜의 하루 범위 밖(제외 날짜, 기간 밖, 하루 범위 밖)은 이 규칙에서 보지 않는다
- 저장할 때의 방식으로 본다. 나중에 방식을 바꿔도 저장된 가능 시간을 다시 보지 않는다
게스트 경로: tests/domain/guest/test_meeting_participation.py
"""
from datetime import date, timedelta

import pytest

HOURLY = {
    "title": "시간",
    "start_date": "2024-02-05",
    "end_date": "2024-02-07",
    "timezone": "UTC",
    "mode": "hourly",
    "start_time": "09:00:00",
    "end_time": "11:00:00",
    "time_slot_minutes": 30,
}
DAILY = {
    "title": "날짜",
    "start_date": "2024-02-05",
    "end_date": "2024-02-07",
    "timezone": "UTC",
    "mode": "daily",
    "start_time": "00:00:00",
    "end_time": "00:00:00",
    "time_slot_minutes": 1440,
}
WEEKLY = {**DAILY, "title": "요일", "mode": "weekly", "end_date": "2024-02-11"}
MEETINGS = {"hourly": HOURLY, "daily": DAILY, "weekly": WEEKLY}


def _slot(day: str, start: str, end: str, kind: str = "available") -> dict:
    """day의 start~end (UTC). end가 24:00이면 다음 날 00:00"""
    end_day = day
    if end == "24:00":
        end_day, end = (date.fromisoformat(day) + timedelta(days=1)).isoformat(), "00:00"
    return {"start_time": f"{day}T{start}:00Z", "end_time": f"{end_day}T{end}:00Z", "kind": kind}


def _whole(day: str, kind: str = "available") -> dict:
    return _slot(day, "00:00", "24:00", kind)


def _span(start: str, end: str, kind: str = "available") -> dict:
    return {"start_time": start, "end_time": end, "kind": kind}


def _setup(client, body: dict) -> tuple[str, str]:
    response = client.post("/v1/meetings", json=body)
    assert response.status_code == 201, response.text
    meeting_id = response.json()["id"]
    participant = client.post(f"/v1/meetings/{meeting_id}/participate", json={"display_name": "참여자"})
    assert participant.status_code in (200, 201), participant.text
    return meeting_id, participant.json()["id"]


def _put(client, meeting_id: str, participant_id: str, slots: list[dict]):
    return client.put(
        f"/v1/meetings/{meeting_id}/availability", params={"participant_id": participant_id}, json=slots,
    )


def _stored(client, meeting_id: str) -> list[tuple[str, str, str]]:
    availability = client.get(f"/v1/meetings/{meeting_id}/availability").json()
    return sorted((s["start_time"], s["end_time"], s["kind"]) for a in availability for s in a["time_slots"])


def _assert_refused(response, mode: str, day: str) -> None:
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert [error["loc"] for error in detail] == [["body"]]
    assert detail[0]["type"] == "value_error"
    assert detail[0]["msg"].startswith(f"Value error, {mode} meetings: ")
    assert "fully covered by available and unavailable time slots" in detail[0]["msg"]
    assert detail[0]["msg"].endswith(f"({day} is not)")


def _accepted(client, body: dict, slots: list[dict]) -> None:
    meeting_id, participant_id = _setup(client, body)
    response = _put(client, meeting_id, participant_id, slots)
    assert response.status_code == 200, response.text
    assert len(_stored(client, meeting_id)) == len(slots)


def _refused(client, body: dict, slots: list[dict], day: str) -> None:
    meeting_id, participant_id = _setup(client, body)
    response = _put(client, meeting_id, participant_id, slots)
    _assert_refused(response, body["mode"], day)
    assert _stored(client, meeting_id) == []


# ============================================================
# available 구간만: 어느 방식이든 받는다
# ============================================================

@pytest.mark.e2e
@pytest.mark.parametrize("mode", MEETINGS)
@pytest.mark.parametrize(
    "slots",
    [
        [],
        [_slot("2024-02-05", "09:00", "10:00")],
        [_slot("2024-02-05", "09:30", "10:00"), _slot("2024-02-06", "10:00", "10:30")],
        [_slot("2024-02-05", "23:00", "24:00")],
    ],
    ids=["none", "part_of_one_day", "parts_of_two_days", "late_part"],
)
def test_only_available_is_accepted(e2e_client, mode, slots):
    _accepted(e2e_client, MEETINGS[mode], slots)


# ============================================================
# hourly: 날마다 따로
# ============================================================

@pytest.mark.e2e
@pytest.mark.parametrize(
    "slots",
    [
        [_slot("2024-02-05", "09:00", "11:00", "unavailable")],
        [_slot("2024-02-05", "09:00", "10:00", "unavailable"), _slot("2024-02-05", "10:00", "11:00")],
        [_slot("2024-02-05", "10:00", "11:00", "unavailable"), _slot("2024-02-05", "09:00", "10:00")],
        # 맞닿은 여러 구간이 함께 채운다
        [_slot("2024-02-05", "09:00", "09:30", "unavailable"), _slot("2024-02-05", "09:30", "10:00"),
         _slot("2024-02-05", "10:00", "10:15"), _slot("2024-02-05", "10:15", "11:00", "unavailable")],
        # 같은 종류끼리 겹쳐도 된다
        [_slot("2024-02-05", "09:00", "10:00", "unavailable"), _slot("2024-02-05", "09:30", "11:00", "unavailable")],
        # 하루 범위를 넘는 구간은 범위 안쪽만 본다
        [_slot("2024-02-05", "08:00", "10:00", "unavailable"), _slot("2024-02-05", "10:00", "12:00")],
    ],
    ids=["all_unavailable", "unavailable_then_available", "available_then_unavailable", "touching_pieces",
         "overlapping_unavailable", "clipped_to_range"],
)
def test_hourly_day_with_unavailable_and_full_coverage_is_accepted(e2e_client, slots):
    _accepted(e2e_client, HOURLY, slots)


@pytest.mark.e2e
def test_hourly_days_are_judged_separately(e2e_client):
    _accepted(e2e_client, HOURLY, [
        _slot("2024-02-05", "09:00", "10:00"),  # 표시한 시간만 가능
        _slot("2024-02-06", "09:00", "10:30", "unavailable"), _slot("2024-02-06", "10:30", "11:00"),  # 채움
        # 2024-02-07은 답하지 않음
    ])


@pytest.mark.e2e
@pytest.mark.parametrize(
    "slots",
    [
        [_slot("2024-02-05", "09:30", "11:00", "unavailable")],  # 처음 한 칸이 빈다
        [_slot("2024-02-05", "09:00", "10:30", "unavailable")],  # 마지막 한 칸이 빈다
        [_slot("2024-02-05", "09:00", "10:00", "unavailable"), _slot("2024-02-05", "10:30", "11:00")],  # 가운데
        [_slot("2024-02-05", "09:30", "10:00"), _slot("2024-02-05", "10:00", "11:00", "unavailable")],
        [_slot("2024-02-05", "09:00", "09:30", "unavailable"), _slot("2024-02-05", "09:30", "10:59")],
        [_slot("2024-02-05", "08:00", "10:00", "unavailable")],  # 범위 밖은 채워도 소용없다
    ],
    ids=["gap_at_start", "gap_at_end", "gap_in_middle", "available_leaves_start_gap", "one_minute_short",
         "outside_part_does_not_count"],
)
def test_hourly_day_with_unavailable_and_gap_is_refused(e2e_client, slots):
    _refused(e2e_client, HOURLY, slots, "2024-02-05")


@pytest.mark.e2e
def test_hourly_gap_on_one_day_is_refused_even_if_other_days_are_fine(e2e_client):
    _refused(e2e_client, HOURLY, [
        _slot("2024-02-05", "09:00", "10:00"),
        _slot("2024-02-06", "09:00", "11:00", "unavailable"),
        _slot("2024-02-07", "09:00", "10:00", "unavailable"),
    ], "2024-02-07")


@pytest.mark.e2e
def test_hourly_unavailable_spanning_two_days_needs_both_days_covered(e2e_client):
    covered_first_day = [
        _slot("2024-02-05", "09:00", "10:00"),
        _span("2024-02-05T10:00:00Z", "2024-02-06T09:30:00Z", "unavailable"),
    ]

    _refused(e2e_client, HOURLY, covered_first_day, "2024-02-06")
    _accepted(e2e_client, HOURLY, covered_first_day + [_slot("2024-02-06", "09:30", "11:00")])


@pytest.mark.e2e
@pytest.mark.parametrize(
    "slot",
    [
        _slot("2024-02-06", "09:00", "10:00", "unavailable"),  # 제외 날짜
        _slot("2024-02-05", "12:00", "13:00", "unavailable"),  # 하루 범위 뒤
        _slot("2024-02-05", "08:00", "09:00", "unavailable"),  # 하루 범위 시작에 맞닿음
        _slot("2024-02-05", "11:00", "11:30", "unavailable"),  # 하루 범위 끝에 맞닿음
        _slot("2024-02-04", "09:00", "11:00", "unavailable"),  # 기간 전
        _slot("2024-02-08", "09:00", "11:00", "unavailable"),  # 기간 뒤
    ],
    ids=["excluded_date", "after_range", "touching_start", "touching_end", "before_period", "after_period"],
)
def test_unavailable_outside_meeting_day_ranges_is_not_judged(e2e_client, slot):
    _accepted(e2e_client, {**HOURLY, "excluded_dates": ["2024-02-06"]}, [slot])


# ============================================================
# daily·weekly: 답 전체로
# ============================================================

@pytest.mark.e2e
@pytest.mark.parametrize(
    "slots",
    [
        [_whole("2024-02-05", "unavailable"), _whole("2024-02-06"), _whole("2024-02-07", "unavailable")],
        [_span("2024-02-05T00:00:00Z", "2024-02-08T00:00:00Z", "unavailable")],
        [_span("2024-02-05T00:00:00Z", "2024-02-06T12:00:00Z", "unavailable"),
         _span("2024-02-06T12:00:00Z", "2024-02-08T00:00:00Z")],
    ],
    ids=["day_by_day", "one_interval", "split_inside_a_day"],
)
def test_daily_all_days_covered_is_accepted(e2e_client, slots):
    _accepted(e2e_client, DAILY, slots)


@pytest.mark.e2e
@pytest.mark.parametrize(
    "slots, day",
    [
        ([_whole("2024-02-05", "unavailable")], "2024-02-06"),
        ([_whole("2024-02-05", "unavailable"), _whole("2024-02-06")], "2024-02-07"),
        ([_whole("2024-02-05"), _whole("2024-02-06"), _whole("2024-02-07", "unavailable")], None),
        ([_slot("2024-02-05", "00:00", "23:59", "unavailable"), _whole("2024-02-06"), _whole("2024-02-07")],
         "2024-02-05"),
        ([_whole("2024-02-05", "unavailable"), _slot("2024-02-06", "00:00", "12:00"), _whole("2024-02-07")],
         "2024-02-06"),
    ],
    ids=["other_days_unanswered", "last_day_unanswered", "all_covered", "first_day_one_minute_short",
         "middle_day_half"],
)
def test_daily_unavailable_needs_every_day_covered(e2e_client, slots, day):
    if day is None:
        _accepted(e2e_client, DAILY, slots)
    else:
        _refused(e2e_client, DAILY, slots, day)


@pytest.mark.e2e
def test_daily_excluded_dates_are_not_required(e2e_client):
    _accepted(e2e_client, {**DAILY, "excluded_dates": ["2024-02-06"]}, [
        _whole("2024-02-05", "unavailable"), _whole("2024-02-07"),
    ])


@pytest.mark.e2e
def test_weekly_unavailable_needs_every_day_covered(e2e_client):
    _refused(e2e_client, WEEKLY, [_whole("2024-02-07", "unavailable")], "2024-02-05")
    _accepted(e2e_client, WEEKLY, [
        _span("2024-02-05T00:00:00Z", "2024-02-08T00:00:00Z"),
        _span("2024-02-08T00:00:00Z", "2024-02-12T00:00:00Z", "unavailable"),
    ])


# ============================================================
# 일광 절약 시간 전환이 있는 날 (America/New_York)
# ============================================================

@pytest.mark.e2e
def test_hourly_day_when_clocks_go_back(e2e_client):
    """2024-11-03 00:00–06:00 EDT/EST는 7시간이다 (04:00Z–11:00Z)"""
    body = {**HOURLY, "timezone": "America/New_York", "start_date": "2024-11-03", "end_date": "2024-11-03",
            "start_time": "00:00:00", "end_time": "06:00:00", "time_slot_minutes": 60}

    _refused(e2e_client, body, [_span("2024-11-03T04:00:00Z", "2024-11-03T10:00:00Z", "unavailable")], "2024-11-03")
    _accepted(e2e_client, body, [_span("2024-11-03T04:00:00Z", "2024-11-03T11:00:00Z", "unavailable")])


@pytest.mark.e2e
def test_daily_days_when_clocks_go_forward(e2e_client):
    """2024-03-10은 23시간(05:00Z–다음 날 04:00Z), 2024-03-11은 04:00Z에 시작한다"""
    body = {**DAILY, "timezone": "America/New_York", "start_date": "2024-03-10", "end_date": "2024-03-11"}
    first_day = _span("2024-03-10T05:00:00Z", "2024-03-11T04:00:00Z", "unavailable")

    _refused(e2e_client, body, [first_day, _span("2024-03-11T05:00:00Z", "2024-03-12T04:00:00Z")], "2024-03-11")
    _accepted(e2e_client, body, [first_day, _span("2024-03-11T04:00:00Z", "2024-03-12T04:00:00Z")])
    _accepted(e2e_client, body, [_span("2024-03-10T05:00:00Z", "2024-03-12T04:00:00Z", "unavailable")])


# ============================================================
# 거절의 모양과 저장된 가능 시간
# ============================================================

@pytest.mark.e2e
def test_refusal_body_and_stored_slots_are_kept(e2e_client):
    meeting_id, participant_id = _setup(e2e_client, HOURLY)
    assert _put(e2e_client, meeting_id, participant_id, [_slot("2024-02-05", "09:00", "10:00")]).status_code == 200
    before = _stored(e2e_client, meeting_id)

    response = _put(e2e_client, meeting_id, participant_id, [
        {"start_time": "2024-02-06T18:00:00+09:00", "end_time": "2024-02-06T19:00:00+09:00", "kind": "unavailable"},
        {"start_time": "2024-02-05T09:00:00", "end_time": "2024-02-05T10:00:00Z"},
    ])

    assert response.status_code == 422, response.text
    assert response.json() == {"detail": [{
        "type": "value_error",
        "loc": ["body"],
        "msg": "Value error, hourly meetings: a day with unavailable time slots must be fully covered by available"
               " and unavailable time slots (2024-02-06 is not)",
        "input": [
            {"start_time": "2024-02-06T09:00:00+0000", "end_time": "2024-02-06T10:00:00+0000", "kind": "unavailable"},
            {"start_time": "2024-02-05T09:00:00+0000", "end_time": "2024-02-05T10:00:00+0000", "kind": "available"},
        ],
        "ctx": {"error": {}},
    }]}
    assert _stored(e2e_client, meeting_id) == before


@pytest.mark.e2e
def test_overlap_is_still_refused_first(e2e_client):
    meeting_id, participant_id = _setup(e2e_client, HOURLY)

    response = _put(e2e_client, meeting_id, participant_id, [
        _slot("2024-02-05", "09:00", "10:00"), _slot("2024-02-05", "09:30", "10:00", "unavailable"),
    ])

    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["msg"] == "Value error, available and unavailable time slots must not overlap"


@pytest.mark.e2e
def test_rule_follows_mode_at_save_time(e2e_client):
    """방식을 바꿔도 저장된 가능 시간은 그대로이고, 다음 저장부터 바뀐 방식으로 본다"""
    meeting_id, participant_id = _setup(e2e_client, {**HOURLY, "start_time": "00:00:00", "end_time": "00:00:00"})
    answer = [_whole("2024-02-05", "unavailable")]
    assert _put(e2e_client, meeting_id, participant_id, answer).status_code == 200
    before = _stored(e2e_client, meeting_id)

    assert e2e_client.patch(f"/v1/meetings/{meeting_id}", json={"mode": "daily"}).status_code == 200

    assert _stored(e2e_client, meeting_id) == before
    _assert_refused(_put(e2e_client, meeting_id, participant_id, answer), "daily", "2024-02-06")
    assert _stored(e2e_client, meeting_id) == before
