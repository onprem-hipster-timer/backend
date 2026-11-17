"""
Meeting 가능 시간 구간의 종류(kind) E2E 테스트

PUT /availability의 구간마다 kind(available, unavailable, 보내지 않으면 available)를 받아 그대로 저장하고 돌려준다.
보낸 구간이 답의 전부다. 보내지 않은 시간은 답하지 않은 것이고 어느 종류로도 채우지 않는다.
결과 그리드의 count는 available 구간만 센다.
"""
import pytest

MEETING = {
    "title": "구간 종류",
    "start_date": "2024-02-05",
    "end_date": "2024-02-06",
    "timezone": "UTC",
    "mode": "hourly",
    "start_time": "09:00:00",
    "end_time": "11:00:00",
    "time_slot_minutes": 30,
}  # 이틀 x 4칸 = 8칸


def _slot(start: str, end: str, kind: str | None = None) -> dict:
    slot = {"start_time": f"2024-02-05T{start}:00Z", "end_time": f"2024-02-05T{end}:00Z"}
    if kind is not None:
        slot["kind"] = kind
    return slot


def _create(client, body: dict = MEETING) -> str:
    response = client.post("/v1/meetings", json=body)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _participate(client, meeting_id: str) -> str:
    response = client.post(f"/v1/meetings/{meeting_id}/participate", json={"display_name": "참여자"})
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


def _put(client, meeting_id: str, participant_id: str, slots: list[dict], **params):
    return client.put(
        f"/v1/meetings/{meeting_id}/availability", params={"participant_id": participant_id, **params}, json=slots,
    )


def _stored(client, meeting_id: str) -> list[tuple[str, str, str]]:
    availability = client.get(f"/v1/meetings/{meeting_id}/availability").json()
    return [(s["start_time"], s["end_time"], s["kind"]) for a in availability for s in a["time_slots"]]


def _counts(client, meeting_id: str) -> dict[str, int]:
    result = client.get(f"/v1/meetings/{meeting_id}/result").json()
    return {cell["start_time"][11:16]: cell["count"] for cell in result["availability_grid"][:4]}


@pytest.mark.e2e
def test_kind_defaults_to_available(e2e_client):
    meeting_id = _create(e2e_client)
    participant_id = _participate(e2e_client, meeting_id)

    response = _put(e2e_client, meeting_id, participant_id, [_slot("09:00", "10:00")])

    assert response.status_code == 200, response.text
    assert [s["kind"] for s in response.json()] == ["available"]
    assert _stored(e2e_client, meeting_id) == [
        ("2024-02-05T09:00:00+0000", "2024-02-05T10:00:00+0000", "available"),
    ]


@pytest.mark.e2e
def test_both_kinds_are_stored_and_returned(e2e_client):
    meeting_id = _create(e2e_client)
    participant_id = _participate(e2e_client, meeting_id)

    response = _put(e2e_client, meeting_id, participant_id, [
        _slot("10:00", "11:00", "unavailable"),
        _slot("09:00", "10:00", "available"),
    ], timezone="Asia/Seoul")

    assert response.status_code == 200, response.text
    assert [(s["start_time"], s["kind"]) for s in response.json()] == [
        ("2024-02-05T19:00:00+0900", "unavailable"),
        ("2024-02-05T18:00:00+0900", "available"),
    ]
    assert _stored(e2e_client, meeting_id) == [
        ("2024-02-05T09:00:00+0000", "2024-02-05T10:00:00+0000", "available"),
        ("2024-02-05T10:00:00+0000", "2024-02-05T11:00:00+0000", "unavailable"),
    ]


@pytest.mark.e2e
@pytest.mark.parametrize("kind", ["busy", "AVAILABLE", "Unavailable", "", None, 1, ["available"]])
def test_unknown_kind_is_422_and_keeps_stored(e2e_client, kind):
    meeting_id = _create(e2e_client)
    participant_id = _participate(e2e_client, meeting_id)
    _put(e2e_client, meeting_id, participant_id, [_slot("09:00", "10:00", "unavailable")])

    response = _put(e2e_client, meeting_id, participant_id, [{**_slot("10:00", "11:00"), "kind": kind}])

    assert response.status_code == 422, response.text
    assert _stored(e2e_client, meeting_id) == [
        ("2024-02-05T09:00:00+0000", "2024-02-05T10:00:00+0000", "unavailable"),
    ]


@pytest.mark.e2e
def test_result_counts_only_available(multi_user_e2e):
    owner = multi_user_e2e.as_user("owner")
    member = multi_user_e2e.as_user("member")
    meeting_id = _create(owner)
    owner.put(f"/v1/visibility/meeting/{meeting_id}", json={"level": "public"})
    _put(owner, meeting_id, _participate(owner, meeting_id), [
        _slot("09:00", "10:00", "unavailable"),
        _slot("10:00", "11:00", "available"),
    ])
    _put(member, meeting_id, _participate(member, meeting_id), [_slot("09:00", "11:00", "unavailable")])

    assert _counts(owner, meeting_id) == {"09:00": 0, "09:30": 0, "10:00": 1, "10:30": 1}


@pytest.mark.e2e
def test_put_replaces_slots_of_both_kinds(e2e_client):
    meeting_id = _create(e2e_client)
    participant_id = _participate(e2e_client, meeting_id)
    _put(e2e_client, meeting_id, participant_id, [
        _slot("09:00", "10:00", "available"), _slot("10:00", "11:00", "unavailable"),
    ])

    assert _put(e2e_client, meeting_id, participant_id, [_slot("09:30", "10:30", "unavailable")]).status_code == 200
    assert _stored(e2e_client, meeting_id) == [
        ("2024-02-05T09:30:00+0000", "2024-02-05T10:30:00+0000", "unavailable"),
    ]
    assert _put(e2e_client, meeting_id, participant_id, []).status_code == 200
    assert _stored(e2e_client, meeting_id) == []


@pytest.mark.e2e
def test_slot_cap_counts_both_kinds(e2e_client):
    meeting_id = _create(e2e_client)
    participant_id = _participate(e2e_client, meeting_id)
    cells = [("09:00", "09:30"), ("09:30", "10:00"), ("10:00", "10:30"), ("10:30", "11:00")]
    slots = [_slot(start, end, "available") for start, end in cells] + [
        {**_slot(start, end, "unavailable"), "start_time": f"2024-02-06T{start}:00Z", "end_time": f"2024-02-06T{end}:00Z"}
        for start, end in cells
    ]

    assert _put(e2e_client, meeting_id, participant_id, slots).status_code == 200
    response = _put(e2e_client, meeting_id, participant_id, slots + [
        {"start_time": "2024-02-07T09:00:00Z", "end_time": "2024-02-07T09:30:00Z", "kind": "unavailable"},
    ])
    assert response.status_code == 422, response.text
    assert response.json()["error_type"] == "TooManyTimeSlotsError"


# ============================================================
# 한 참여자의 available 구간과 unavailable 구간은 겹칠 수 없다 (맞닿는 것은 된다)
# ============================================================

@pytest.mark.e2e
@pytest.mark.parametrize(
    "slots",
    [
        [_slot("09:00", "10:00", "available"), _slot("09:30", "10:30", "unavailable")],
        [_slot("09:30", "10:30", "unavailable"), _slot("09:00", "10:00", "available")],
        [_slot("09:00", "10:00", "available"), _slot("09:00", "10:00", "unavailable")],  # 같은 구간
        [_slot("09:00", "10:00"), _slot("09:00", "10:00", "unavailable")],  # kind 없으면 available
        [_slot("09:00", "11:00", "unavailable"), _slot("09:30", "10:00")],  # 안에 들어간다
        [_slot("09:30", "10:00", "unavailable"), _slot("09:00", "11:00")],
        # 맞닿은 available 둘을 합친 구간과 겹친다
        [_slot("09:00", "09:30"), _slot("09:30", "10:00"), _slot("09:20", "09:40", "unavailable")],
        # 먼 available 뒤 겹치는 available
        [_slot("10:30", "11:00", "unavailable"), _slot("09:00", "09:15"), _slot("09:15", "10:31")],
        [{"start_time": "2024-02-05T09:00:00Z", "end_time": "2024-02-06T10:00:00Z", "kind": "available"},
         {"start_time": "2024-02-06T09:00:00Z", "end_time": "2024-02-06T09:30:00Z", "kind": "unavailable"}],
        [{"start_time": "2024-02-05T09:00:00Z", "end_time": "2024-02-05T10:00:01Z", "kind": "available"},
         _slot("10:00", "10:30", "unavailable")],
        # 같은 시각을 다른 오프셋으로
        [{"start_time": "2024-02-05T18:00:00+09:00", "end_time": "2024-02-05T19:00:00+09:00"},
         _slot("09:59", "10:30", "unavailable")],
    ],
)
def test_overlapping_available_and_unavailable_is_422_and_keeps_stored(e2e_client, slots):
    meeting_id = _create(e2e_client)
    participant_id = _participate(e2e_client, meeting_id)
    _put(e2e_client, meeting_id, participant_id, [_slot("09:00", "09:30", "unavailable")])
    before = _stored(e2e_client, meeting_id)

    response = _put(e2e_client, meeting_id, participant_id, slots)

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert [error["loc"] for error in detail] == [["body"]]
    assert "overlap" in detail[0]["msg"]
    assert _stored(e2e_client, meeting_id) == before


@pytest.mark.e2e
@pytest.mark.parametrize(
    "slots",
    [
        [_slot("09:00", "10:00", "available"), _slot("10:00", "11:00", "unavailable")],  # 맞닿는다
        [_slot("10:00", "11:00", "available"), _slot("09:00", "10:00", "unavailable")],
        [_slot("09:00", "09:30", "unavailable"), _slot("09:30", "10:00"), _slot("10:00", "10:30", "unavailable")],
        [_slot("09:00", "10:00"), _slot("09:30", "10:30")],  # 같은 종류는 겹쳐도 된다
        [_slot("09:00", "10:00", "unavailable"), _slot("09:00", "10:00", "unavailable")],
        [_slot("09:00", "09:30", "unavailable"), _slot("09:15", "10:00", "unavailable"), _slot("10:00", "11:00")],
    ],
)
def test_touching_kinds_and_overlapping_same_kind_accepted(e2e_client, slots):
    meeting_id = _create(e2e_client)
    participant_id = _participate(e2e_client, meeting_id)

    response = _put(e2e_client, meeting_id, participant_id, slots)

    assert response.status_code == 200, response.text
    assert len(_stored(e2e_client, meeting_id)) == len(slots)


@pytest.mark.e2e
def test_different_participants_may_overlap_with_different_kinds(multi_user_e2e):
    owner = multi_user_e2e.as_user("owner")
    member = multi_user_e2e.as_user("member")
    meeting_id = _create(owner)
    owner.put(f"/v1/visibility/meeting/{meeting_id}", json={"level": "public"})

    assert _put(owner, meeting_id, _participate(owner, meeting_id), [_slot("09:00", "10:00")]).status_code == 200
    assert _put(
        member, meeting_id, _participate(member, meeting_id), [_slot("09:00", "10:00", "unavailable")],
    ).status_code == 200


# ============================================================
# 결과 칸의 unavailable_count: 그 칸을 모두 덮는 unavailable 구간을 가진 참여자 수
# ============================================================

def _cells(client, meeting_id: str, **params) -> dict[str, tuple[int, int]]:
    """첫날 칸 시작 시각(HH:MM) → (count, unavailable_count)"""
    result = client.get(f"/v1/meetings/{meeting_id}/result", params=params).json()
    return {
        cell["start_time"][11:16]: (cell["count"], cell["unavailable_count"])
        for cell in result["availability_grid"][:4]
    }


@pytest.mark.e2e
def test_unavailable_count_counts_participants_covering_whole_cell(multi_user_e2e):
    owner = multi_user_e2e.as_user("owner")
    member = multi_user_e2e.as_user("member")
    other = multi_user_e2e.as_user("other")
    meeting_id = _create(owner)
    owner.put(f"/v1/visibility/meeting/{meeting_id}", json={"level": "public"})
    assert _put(owner, meeting_id, _participate(owner, meeting_id), [
        _slot("09:00", "10:00", "unavailable"), _slot("10:00", "10:30", "available"),
    ]).status_code == 200
    # 칸의 일부만 덮는 구간은 세지 않는다
    assert _put(member, meeting_id, _participate(member, meeting_id), [
        _slot("09:15", "09:45", "unavailable"), _slot("10:30", "11:00", "unavailable"),
    ]).status_code == 200
    # 맞닿은 구간은 함께 칸을 덮고, 같은 구간을 여러 번 보내도 한 번 센다
    assert _put(other, meeting_id, _participate(other, meeting_id), [
        _slot("09:00", "09:20", "unavailable"), _slot("09:20", "10:00", "unavailable"),
        _slot("09:00", "10:00", "unavailable"),
    ]).status_code == 200

    assert _cells(owner, meeting_id) == {
        "09:00": (0, 2), "09:30": (0, 2), "10:00": (1, 0), "10:30": (0, 1),
    }
    assert _cells(owner, meeting_id, timezone="Asia/Seoul") == {
        "18:00": (0, 2), "18:30": (0, 2), "19:00": (1, 0), "19:30": (0, 1),
    }


@pytest.mark.e2e
def test_unavailable_count_is_zero_without_unavailable_slots(e2e_client):
    meeting_id = _create(e2e_client)
    _put(e2e_client, meeting_id, _participate(e2e_client, meeting_id), [_slot("09:00", "11:00")])

    result = e2e_client.get(f"/v1/meetings/{meeting_id}/result").json()

    assert [cell["unavailable_count"] for cell in result["availability_grid"]] == [0] * 8
    assert [cell["count"] for cell in result["availability_grid"]] == [1] * 4 + [0] * 4


# ============================================================
# 보낸 구간이 답의 전부다: 하루 범위를 다 채우지 않아도 받고, 빈 시간은 답하지 않은 것이다
# ============================================================

DAILY = {
    **MEETING,
    "title": "날짜",
    "mode": "daily",
    "end_date": "2024-02-07",
    "start_time": "00:00:00",
    "end_time": "00:00:00",
    "time_slot_minutes": 1440,
}  # 사흘 x 1칸
WEEKLY = {**DAILY, "title": "요일", "mode": "weekly", "end_date": "2024-02-11"}  # 이레 x 1칸


def _as_stored(slot: dict) -> tuple[str, str, str]:
    """UTC("Z")로 보낸 구간이 저장되어 돌아오는 모양"""
    return (
        slot["start_time"].replace("Z", "+0000"),
        slot["end_time"].replace("Z", "+0000"),
        slot.get("kind", "available"),
    )


@pytest.mark.e2e
@pytest.mark.parametrize(
    "slots",
    [
        [_slot("09:30", "10:00", "unavailable")],
        [_slot("09:00", "09:30", "unavailable"), _slot("10:30", "11:00", "unavailable")],
        [_slot("09:00", "09:30", "unavailable"), _slot("10:00", "10:30")],
        [_slot("09:30", "10:00"), _slot("10:00", "10:30", "unavailable")],
        [_slot("10:00", "11:00", "unavailable"),
         {"start_time": "2024-02-06T09:00:00Z", "end_time": "2024-02-06T09:30:00Z", "kind": "unavailable"},
         {"start_time": "2024-02-06T10:00:00Z", "end_time": "2024-02-06T10:30:00Z"}],
    ],
    ids=["only_unavailable", "unavailable_with_gap", "both_kinds_with_gaps", "touching_kinds_with_gaps", "two_days"],
)
def test_hourly_answer_with_unpainted_time_is_stored_as_sent(e2e_client, slots):
    meeting_id = _create(e2e_client)
    participant_id = _participate(e2e_client, meeting_id)

    response = _put(e2e_client, meeting_id, participant_id, slots)

    assert response.status_code == 200, response.text
    assert _stored(e2e_client, meeting_id) == sorted(_as_stored(slot) for slot in slots)


@pytest.mark.e2e
def test_unpainted_cells_are_neither_available_nor_unavailable(e2e_client):
    meeting_id = _create(e2e_client)
    assert _put(e2e_client, meeting_id, _participate(e2e_client, meeting_id), [
        _slot("09:00", "09:30", "unavailable"), _slot("10:00", "10:30"),
    ]).status_code == 200

    assert _cells(e2e_client, meeting_id) == {"09:00": (0, 1), "09:30": (0, 0), "10:00": (1, 0), "10:30": (0, 0)}


@pytest.mark.e2e
@pytest.mark.parametrize("body, days", [(DAILY, 3), (WEEKLY, 7)], ids=["daily", "weekly"])
def test_one_unavailable_day_leaves_other_days_unanswered(e2e_client, body, days):
    meeting_id = _create(e2e_client, body)
    participant_id = _participate(e2e_client, meeting_id)
    second_day = {"start_time": "2024-02-06T00:00:00Z", "end_time": "2024-02-07T00:00:00Z", "kind": "unavailable"}

    assert _put(e2e_client, meeting_id, participant_id, [second_day]).status_code == 200

    assert _stored(e2e_client, meeting_id) == [_as_stored(second_day)]
    grid = e2e_client.get(f"/v1/meetings/{meeting_id}/result").json()["availability_grid"]
    assert [(cell["count"], cell["unavailable_count"]) for cell in grid] == [(0, 0), (0, 1)] + [(0, 0)] * (days - 2)
