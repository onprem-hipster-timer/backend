"""
Meeting 시간대·가능 시간 구간 E2E 테스트

미팅의 날짜·요일·시간은 미팅 시간대의 벽시계 값이고, 가능 시간은 받은 그대로 저장하는 UTC 구간 [start, end)이다.
결과 그리드는 미팅 규칙으로 만든 칸마다 그 칸을 모두 덮는 가능 시간을 가진 참여자 수를 센다.
"""
from datetime import datetime, timedelta, timezone

import pytest

SEOUL_MEETING = {
    "title": "시간대 테스트",
    "start_date": "2024-02-05",  # 월요일
    "end_date": "2024-02-06",
    "timezone": "Asia/Seoul",
    "mode": "hourly",
    "available_days": [0, 1],
    "start_time": "09:00:00",
    "end_time": "12:00:00",
    "time_slot_minutes": 30,
}


def _create_meeting(client, **overrides) -> str:
    response = client.post("/v1/meetings", json={**SEOUL_MEETING, **overrides})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _participate(client, meeting_id: str) -> str:
    response = client.post(f"/v1/meetings/{meeting_id}/participate", json={"display_name": "참여자"})
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


def _put(client, meeting_id: str, participant_id: str, slots: list[dict], **params):
    return client.put(
        f"/v1/meetings/{meeting_id}/availability",
        params={"participant_id": participant_id, **params},
        json=slots,
    )


def _grid(client, meeting_id: str, **params) -> list[tuple[datetime, datetime, int]]:
    response = client.get(f"/v1/meetings/{meeting_id}/result", params=params)
    assert response.status_code == 200, response.text
    return [
        (datetime.fromisoformat(c["start_time"]), datetime.fromisoformat(c["end_time"]), c["count"])
        for c in response.json()["availability_grid"]
    ]


def _counts(client, meeting_id: str) -> dict[datetime, int]:
    return {start: count for start, _, count in _grid(client, meeting_id)}


def _stored(client, meeting_id: str, **params) -> list[tuple[str, str]]:
    availability = client.get(f"/v1/meetings/{meeting_id}/availability", params=params).json()
    return [(s["start_time"], s["end_time"]) for a in availability for s in a["time_slots"]]


def _utc(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


# ============================================================
# 결과 그리드: 미팅 시간대에서 만든 칸
# ============================================================

@pytest.mark.e2e
def test_grid_cells_are_meeting_wall_clock_in_its_time_zone(e2e_client):
    meeting_id = _create_meeting(e2e_client)

    grid = _grid(e2e_client, meeting_id)

    # 서울 09:00–12:00 = UTC 00:00–03:00, 이틀 x 6칸
    assert len(grid) == 12
    assert grid[0][:2] == (_utc(2024, 2, 5, 0, 0), _utc(2024, 2, 5, 0, 30))
    assert grid[5][:2] == (_utc(2024, 2, 5, 2, 30), _utc(2024, 2, 5, 3, 0))
    assert grid[6][:2] == (_utc(2024, 2, 6, 0, 0), _utc(2024, 2, 6, 0, 30))
    assert [start for start, _, _ in grid] == sorted(start for start, _, _ in grid)


@pytest.mark.e2e
def test_slot_with_other_offset_lands_in_matching_cells(e2e_client):
    meeting_id = _create_meeting(e2e_client)
    participant_id = _participate(e2e_client, meeting_id)

    # 2024-02-04 19:00–20:00 (-05:00) = 2024-02-05 00:00–01:00 UTC = 서울 09:00–10:00
    response = _put(e2e_client, meeting_id, participant_id, [
        {"start_time": "2024-02-04T19:00:00-05:00", "end_time": "2024-02-04T20:00:00-05:00"},
    ])

    assert response.status_code == 200, response.text
    assert response.json()[0]["start_time"] == "2024-02-05T00:00:00+0000"
    counted = [start for start, count in _counts(e2e_client, meeting_id).items() if count]
    assert counted == [_utc(2024, 2, 5, 0, 0), _utc(2024, 2, 5, 0, 30)]


@pytest.mark.e2e
def test_result_timezone_query_returns_same_instants(e2e_client):
    meeting_id = _create_meeting(e2e_client)
    participant_id = _participate(e2e_client, meeting_id)
    _put(e2e_client, meeting_id, participant_id, [
        {"start_time": "2024-02-05T09:00:00+09:00", "end_time": "2024-02-05T10:00:00+09:00"},
    ])

    utc_grid = _grid(e2e_client, meeting_id)
    new_york_grid = _grid(e2e_client, meeting_id, timezone="America/New_York")

    assert new_york_grid == utc_grid  # aware datetime 비교: 같은 시각
    raw = e2e_client.get(
        f"/v1/meetings/{meeting_id}/result", params={"timezone": "America/New_York"},
    ).json()["availability_grid"][0]
    assert raw["start_time"] == "2024-02-04T19:00:00-0500"


@pytest.mark.e2e
def test_whole_day_meeting_counts_whole_day_slot_in_last_cell(e2e_client):
    meeting_id = _create_meeting(
        e2e_client, start_date="2024-02-05", end_date="2024-02-05",
        start_time="00:00:00", end_time="00:00:00", time_slot_minutes=30,
    )
    participant_id = _participate(e2e_client, meeting_id)

    response = _put(e2e_client, meeting_id, participant_id, [
        {"start_time": "2024-02-05T00:00:00+09:00", "end_time": "2024-02-06T00:00:00+09:00"},
    ])

    assert response.status_code == 200, response.text
    grid = _grid(e2e_client, meeting_id)
    assert len(grid) == 48
    assert grid[-1] == (_utc(2024, 2, 5, 14, 30), _utc(2024, 2, 5, 15, 0), 1)  # 서울 23:30–24:00
    assert all(count == 1 for _, _, count in grid)


@pytest.mark.e2e
def test_dst_day_cells_are_consecutive_instants(e2e_client):
    """뉴욕 2024-03-10은 02:00이 03:00으로 건너뛰어 23시간이다"""
    meeting_id = _create_meeting(
        e2e_client, start_date="2024-03-10", end_date="2024-03-10", timezone="America/New_York",
        available_days=[6], start_time="00:00:00", end_time="00:00:00", time_slot_minutes=60,
    )

    grid = _grid(e2e_client, meeting_id)

    assert len(grid) == 23
    assert grid[0][0] == _utc(2024, 3, 10, 5)  # 00:00 EST
    assert grid[-1][1] == _utc(2024, 3, 11, 4)  # 다음 날 00:00 EDT
    assert all(end - start == timedelta(hours=1) for start, end, _ in grid)
    assert all(grid[i][1] == grid[i + 1][0] for i in range(len(grid) - 1))
    raw = e2e_client.get(
        f"/v1/meetings/{meeting_id}/result", params={"timezone": "America/New_York"},
    ).json()["availability_grid"]
    assert [c["start_time"][11:16] for c in raw[1:3]] == ["01:00", "03:00"]


# ============================================================
# 세기: 칸을 모두 덮어야 하고, 참여자마다 한 번
# ============================================================

@pytest.mark.e2e
def test_slot_covering_part_of_cell_is_not_counted(e2e_client):
    meeting_id = _create_meeting(e2e_client)
    participant_id = _participate(e2e_client, meeting_id)

    _put(e2e_client, meeting_id, participant_id, [
        {"start_time": "2024-02-05T09:10:00+09:00", "end_time": "2024-02-05T10:00:00+09:00"},
    ])

    counts = _counts(e2e_client, meeting_id)
    assert counts[_utc(2024, 2, 5, 0, 0)] == 0
    assert counts[_utc(2024, 2, 5, 0, 30)] == 1


@pytest.mark.e2e
def test_duplicate_and_overlapping_slots_count_once(e2e_client):
    meeting_id = _create_meeting(e2e_client)
    participant_id = _participate(e2e_client, meeting_id)
    slot = {"start_time": "2024-02-05T09:00:00+09:00", "end_time": "2024-02-05T10:00:00+09:00"}

    response = _put(e2e_client, meeting_id, participant_id, [
        slot, slot,
        {"start_time": "2024-02-05T09:30:00+09:00", "end_time": "2024-02-05T11:00:00+09:00"},
    ])

    assert response.status_code == 200, response.text
    assert len(_stored(e2e_client, meeting_id)) == 3
    counts = _counts(e2e_client, meeting_id)
    assert [counts[_utc(2024, 2, 5, 0, m)] for m in (0, 30)] == [1, 1]
    assert [counts[_utc(2024, 2, 5, 1, m)] for m in (0, 30)] == [1, 1]
    assert max(counts.values()) == 1


@pytest.mark.e2e
def test_adjacent_slots_of_one_participant_cover_cell_together(e2e_client):
    meeting_id = _create_meeting(e2e_client)
    participant_id = _participate(e2e_client, meeting_id)

    _put(e2e_client, meeting_id, participant_id, [
        {"start_time": "2024-02-05T09:15:00+09:00", "end_time": "2024-02-05T09:30:00+09:00"},
        {"start_time": "2024-02-05T09:00:00+09:00", "end_time": "2024-02-05T09:15:00+09:00"},
    ])

    counts = _counts(e2e_client, meeting_id)
    assert counts[_utc(2024, 2, 5, 0, 0)] == 1
    assert counts[_utc(2024, 2, 5, 0, 30)] == 0


@pytest.mark.e2e
def test_slots_of_different_participants_do_not_combine(multi_user_e2e):
    owner = multi_user_e2e.as_user("owner")
    member = multi_user_e2e.as_user("member")
    meeting_id = _create_meeting(owner)
    owner.put(f"/v1/visibility/meeting/{meeting_id}", json={"level": "public"})

    _put(owner, meeting_id, _participate(owner, meeting_id), [
        {"start_time": "2024-02-05T09:00:00+09:00", "end_time": "2024-02-05T09:15:00+09:00"},
    ])
    _put(member, meeting_id, _participate(member, meeting_id), [
        {"start_time": "2024-02-05T09:15:00+09:00", "end_time": "2024-02-05T09:30:00+09:00"},
    ])

    assert _counts(owner, meeting_id)[_utc(2024, 2, 5, 0, 0)] == 0


# ============================================================
# 저장: 받은 구간 그대로
# ============================================================

@pytest.mark.e2e
def test_unaligned_slot_is_stored_exactly(e2e_client):
    meeting_id = _create_meeting(e2e_client)
    participant_id = _participate(e2e_client, meeting_id)

    response = _put(e2e_client, meeting_id, participant_id, [
        {"start_time": "2024-02-05T09:07:00+09:00", "end_time": "2024-02-05T10:43:00+09:00"},
    ])

    assert response.status_code == 200, response.text
    assert _stored(e2e_client, meeting_id) == [("2024-02-05T00:07:00+0000", "2024-02-05T01:43:00+0000")]
    counted = [start for start, count in _counts(e2e_client, meeting_id).items() if count]
    assert counted == [_utc(2024, 2, 5, 0, 30), _utc(2024, 2, 5, 1, 0)]


@pytest.mark.e2e
def test_slot_outside_meeting_is_stored_and_not_in_result(e2e_client):
    meeting_id = _create_meeting(e2e_client)
    participant_id = _participate(e2e_client, meeting_id)

    response = _put(e2e_client, meeting_id, participant_id, [
        {"start_time": "2024-03-01T09:00:00+09:00", "end_time": "2024-03-01T12:00:00+09:00"},  # 기간 밖
        {"start_time": "2024-02-05T13:00:00+09:00", "end_time": "2024-02-05T15:00:00+09:00"},  # 하루 범위 밖
    ])

    assert response.status_code == 200, response.text
    assert len(_stored(e2e_client, meeting_id)) == 2
    assert all(count == 0 for _, _, count in _grid(e2e_client, meeting_id))


@pytest.mark.e2e
def test_long_slot_spanning_days_is_one_row_and_counts_in_every_covered_cell(e2e_client):
    meeting_id = _create_meeting(e2e_client)
    participant_id = _participate(e2e_client, meeting_id)

    response = _put(e2e_client, meeting_id, participant_id, [
        {"start_time": "2024-02-05T10:00:00+09:00", "end_time": "2024-02-06T10:00:00+09:00"},
    ])

    assert response.status_code == 200, response.text
    assert _stored(e2e_client, meeting_id) == [("2024-02-05T01:00:00+0000", "2024-02-06T01:00:00+0000")]
    counted = [start for start, count in _counts(e2e_client, meeting_id).items() if count]
    assert counted == [
        _utc(2024, 2, 5, 1, 0), _utc(2024, 2, 5, 1, 30), _utc(2024, 2, 5, 2, 0), _utc(2024, 2, 5, 2, 30),
        _utc(2024, 2, 6, 0, 0), _utc(2024, 2, 6, 0, 30),
    ]


@pytest.mark.e2e
def test_slot_without_offset_is_utc(e2e_client):
    meeting_id = _create_meeting(e2e_client)
    participant_id = _participate(e2e_client, meeting_id)

    response = _put(e2e_client, meeting_id, participant_id, [
        {"start_time": "2024-02-05T00:00:00", "end_time": "2024-02-05T00:30:00"},
    ])

    assert response.status_code == 200, response.text
    assert _counts(e2e_client, meeting_id)[_utc(2024, 2, 5, 0, 0)] == 1


@pytest.mark.e2e
@pytest.mark.parametrize(
    "slot",
    [
        {"start_time": "2024-02-05T10:00:00Z", "end_time": "2024-02-05T10:00:00Z"},
        {"start_time": "2024-02-05T10:00:00Z", "end_time": "2024-02-05T09:00:00Z"},
        # 같은 시각을 다른 오프셋으로: 끝이 시작보다 앞
        {"start_time": "2024-02-05T10:00:00+09:00", "end_time": "2024-02-05T02:00:00+01:00"},
        {"start_time": "not a time", "end_time": "2024-02-05T09:00:00Z"},
        {"start_time": "2024-02-05T09:00:00Z"},
    ],
)
def test_invalid_slot_rejected_and_stored_kept(e2e_client, slot):
    meeting_id = _create_meeting(e2e_client)
    participant_id = _participate(e2e_client, meeting_id)
    keep = {"start_time": "2024-02-05T00:00:00Z", "end_time": "2024-02-05T01:00:00Z"}
    _put(e2e_client, meeting_id, participant_id, [keep])

    response = _put(e2e_client, meeting_id, participant_id, [slot])

    assert response.status_code == 422, response.text
    assert _stored(e2e_client, meeting_id) == [("2024-02-05T00:00:00+0000", "2024-02-05T01:00:00+0000")]


@pytest.mark.e2e
def test_availability_timezone_query_converts_slots(e2e_client):
    meeting_id = _create_meeting(e2e_client)
    participant_id = _participate(e2e_client, meeting_id)
    slot = {"start_time": "2024-02-05T00:00:00Z", "end_time": "2024-02-05T01:00:00Z"}

    put_response = _put(e2e_client, meeting_id, participant_id, [slot], timezone="Asia/Seoul")

    assert put_response.status_code == 200, put_response.text
    assert put_response.json()[0]["start_time"] == "2024-02-05T09:00:00+0900"
    assert _stored(e2e_client, meeting_id, timezone="+09:00") == [
        ("2024-02-05T09:00:00+0900", "2024-02-05T10:00:00+0900"),
    ]
    assert _stored(e2e_client, meeting_id) == [("2024-02-05T00:00:00+0000", "2024-02-05T01:00:00+0000")]


# ============================================================
# 미팅 수정: 저장된 가능 시간은 그대로, 그리드만 새 규칙으로
# ============================================================

@pytest.mark.e2e
def test_patch_timezone_keeps_slots_and_rebuilds_grid(e2e_client):
    meeting_id = _create_meeting(e2e_client)
    participant_id = _participate(e2e_client, meeting_id)
    # 서울 2024-02-05 09:00–10:00 = UTC 00:00–01:00 = 뉴욕 2024-02-04 19:00–20:00
    _put(e2e_client, meeting_id, participant_id, [
        {"start_time": "2024-02-05T00:00:00Z", "end_time": "2024-02-05T01:00:00Z"},
    ])
    before = _stored(e2e_client, meeting_id)

    response = e2e_client.patch(f"/v1/meetings/{meeting_id}", json={"timezone": "America/New_York"})

    assert response.status_code == 200, response.text
    assert response.json()["timezone"] == "America/New_York"
    assert _stored(e2e_client, meeting_id) == before
    grid = _grid(e2e_client, meeting_id)
    # 뉴욕 09:00–12:00 = UTC 14:00–17:00, 같은 슬롯은 이 칸들을 덮지 않는다
    assert grid[0][:2] == (_utc(2024, 2, 5, 14, 0), _utc(2024, 2, 5, 14, 30))
    assert all(count == 0 for _, _, count in grid)

    e2e_client.patch(f"/v1/meetings/{meeting_id}", json={"start_date": "2024-02-04", "available_days": [6, 0, 1],
                                                          "start_time": "19:00:00", "end_time": "20:00:00"})
    assert _stored(e2e_client, meeting_id) == before
    counted = [start for start, count in _counts(e2e_client, meeting_id).items() if count]
    assert counted == [_utc(2024, 2, 5, 0, 0), _utc(2024, 2, 5, 0, 30)]
