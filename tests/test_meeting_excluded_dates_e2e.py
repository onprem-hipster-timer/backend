"""
Meeting 제외 날짜(excluded_dates) E2E 테스트

미팅의 날짜는 start_date~end_date에서 excluded_dates를 뺀 날이다. 제외 날짜는 기간 안쪽(첫날·마지막 날이 아닌 날)에만 두고,
겹칠 수 없고, 정렬해 저장한다. 첫날과 마지막 날은 언제나 미팅 날짜다.
"""
import pytest

MEETING = {
    "title": "제외 날짜",
    "start_date": "2024-02-05",  # 월요일
    "end_date": "2024-02-11",  # 일요일
    "timezone": "UTC",
    "mode": "hourly",
    "start_time": "09:00:00",
    "end_time": "10:00:00",
    "time_slot_minutes": 30,
}


def _create(client, **overrides) -> dict:
    response = client.post("/v1/meetings", json={**MEETING, **overrides})
    assert response.status_code == 201, response.text
    return response.json()


def _participate(client, meeting_id: str) -> str:
    response = client.post(f"/v1/meetings/{meeting_id}/participate", json={"display_name": "참여자"})
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


def _put(client, meeting_id: str, participant_id: str, slots: list[dict]):
    return client.put(
        f"/v1/meetings/{meeting_id}/availability", params={"participant_id": participant_id}, json=slots,
    )


def _grid(client, meeting_id: str) -> list[dict]:
    response = client.get(f"/v1/meetings/{meeting_id}/result")
    assert response.status_code == 200, response.text
    return response.json()["availability_grid"]


def _grid_days(client, meeting_id: str) -> list[str]:
    return sorted({cell["start_time"][:10] for cell in _grid(client, meeting_id)})


# ============================================================
# 생성
# ============================================================

@pytest.mark.e2e
def test_excluded_dates_default_to_empty(e2e_client):
    meeting = _create(e2e_client)

    assert meeting["excluded_dates"] == []
    assert _grid_days(e2e_client, meeting["id"]) == [
        "2024-02-05", "2024-02-06", "2024-02-07", "2024-02-08", "2024-02-09", "2024-02-10", "2024-02-11",
    ]


@pytest.mark.e2e
def test_excluded_dates_are_stored_sorted(e2e_client):
    meeting = _create(e2e_client, excluded_dates=["2024-02-10", "2024-02-06", "2024-02-08"])

    assert meeting["excluded_dates"] == ["2024-02-06", "2024-02-08", "2024-02-10"]
    stored = e2e_client.get(f"/v1/meetings/{meeting['id']}").json()
    assert stored["excluded_dates"] == ["2024-02-06", "2024-02-08", "2024-02-10"]


@pytest.mark.e2e
@pytest.mark.parametrize(
    "overrides",
    [
        {"excluded_dates": ["2024-02-06"]},  # 둘째 날
        {"excluded_dates": ["2024-02-10"]},  # 마지막 날 전날
        {"excluded_dates": ["2024-02-06", "2024-02-07", "2024-02-08", "2024-02-09", "2024-02-10"]},  # 안쪽 모두
        {"start_date": "2024-02-05", "end_date": "2024-02-07", "excluded_dates": ["2024-02-06"]},  # 사흘 중 가운데
        {"start_date": "2024-02-05", "end_date": "2024-02-05", "excluded_dates": []},  # 하루
    ],
)
def test_excluded_dates_inside_period_accepted(e2e_client, overrides):
    response = e2e_client.post("/v1/meetings", json={**MEETING, **overrides})

    assert response.status_code == 201, response.text
    assert response.json()["excluded_dates"] == overrides["excluded_dates"]


@pytest.mark.e2e
@pytest.mark.parametrize(
    "overrides",
    [
        {"excluded_dates": ["2024-02-05"]},  # 첫날
        {"excluded_dates": ["2024-02-11"]},  # 마지막 날
        {"excluded_dates": ["2024-02-06", "2024-02-11"]},
        {"excluded_dates": ["2024-02-04"]},  # 기간 앞
        {"excluded_dates": ["2024-02-12"]},  # 기간 뒤
        {"excluded_dates": ["2025-02-07"]},
        {"excluded_dates": ["2024-02-06", "2024-02-06"]},  # 중복
        {"excluded_dates": ["2024-02-08", "2024-02-06", "2024-02-08"]},
        {"excluded_dates": ["2024-02-30"]},
        {"excluded_dates": ["tomorrow"]},
        {"excluded_dates": [None]},
        {"excluded_dates": "2024-02-06"},
        {"excluded_dates": None},
        {"start_date": "2024-02-05", "end_date": "2024-02-05", "excluded_dates": ["2024-02-05"]},  # 하루
        {"start_date": "2024-02-05", "end_date": "2024-02-06", "excluded_dates": ["2024-02-06"]},  # 이틀: 안쪽이 없다
    ],
)
def test_excluded_dates_rejected(e2e_client, overrides):
    response = e2e_client.post("/v1/meetings", json={**MEETING, **overrides})

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert all("excluded_dates" in error["loc"] or "excluded_dates" in error["msg"] for error in detail), detail
    assert e2e_client.get("/v1/meetings").json() == []


@pytest.mark.e2e
def test_available_days_is_not_a_meeting_field(e2e_client):
    """보낸 available_days는 읽지 않는다"""
    meeting = _create(e2e_client, available_days=[0])

    assert "available_days" not in meeting
    assert len(_grid_days(e2e_client, meeting["id"])) == 7


# ============================================================
# 결과 그리드와 슬롯 수
# ============================================================

@pytest.mark.e2e
def test_grid_skips_excluded_dates(e2e_client):
    meeting_id = _create(e2e_client, excluded_dates=["2024-02-06", "2024-02-08"])["id"]

    grid = _grid(e2e_client, meeting_id)

    assert _grid_days(e2e_client, meeting_id) == [
        "2024-02-05", "2024-02-07", "2024-02-09", "2024-02-10", "2024-02-11",
    ]
    assert len(grid) == 5 * 2
    assert [cell["start_time"] for cell in grid[:4]] == [
        "2024-02-05T09:00:00+0000", "2024-02-05T09:30:00+0000",
        "2024-02-07T09:00:00+0000", "2024-02-07T09:30:00+0000",
    ]


@pytest.mark.e2e
def test_slot_on_excluded_date_is_stored_and_not_in_grid(e2e_client):
    meeting_id = _create(e2e_client, excluded_dates=["2024-02-06"])["id"]
    participant_id = _participate(e2e_client, meeting_id)

    response = _put(e2e_client, meeting_id, participant_id, [
        {"start_time": "2024-02-06T09:00:00Z", "end_time": "2024-02-06T10:00:00Z"},
    ])

    assert response.status_code == 200, response.text
    availability = e2e_client.get(f"/v1/meetings/{meeting_id}/availability").json()
    assert len(availability[0]["time_slots"]) == 1
    assert all(cell["count"] == 0 for cell in _grid(e2e_client, meeting_id))


@pytest.mark.e2e
def test_slot_cap_counts_only_meeting_dates(e2e_client):
    # 7일 - 제외 2일 = 5일 x 2칸 = 10칸
    meeting_id = _create(e2e_client, excluded_dates=["2024-02-06", "2024-02-08"])["id"]
    participant_id = _participate(e2e_client, meeting_id)
    slots = [
        {"start_time": f"2024-03-01T00:{i:02d}:00Z", "end_time": f"2024-03-01T00:{i + 1:02d}:00Z"}
        for i in range(11)
    ]

    assert _put(e2e_client, meeting_id, participant_id, slots[:10]).status_code == 200
    assert _put(e2e_client, meeting_id, participant_id, slots).status_code == 422


# ============================================================
# 수정: 저장된 값에 수정 내용을 합친 미팅을 검증한다
# ============================================================

@pytest.mark.e2e
@pytest.mark.parametrize(
    "patch, expected",
    [
        ({"excluded_dates": ["2024-02-09", "2024-02-07"]}, ["2024-02-07", "2024-02-09"]),
        ({"excluded_dates": []}, []),
        ({"end_date": "2024-02-09"}, ["2024-02-08"]),  # 제외 날짜가 여전히 안쪽
        ({"start_date": "2024-02-07"}, ["2024-02-08"]),
        ({"end_date": "2024-02-07", "excluded_dates": ["2024-02-06"]}, ["2024-02-06"]),
        ({"start_date": "2024-02-09", "end_date": "2024-02-12", "excluded_dates": []}, []),
    ],
)
def test_patch_excluded_dates_applied(e2e_client, patch, expected):
    meeting_id = _create(e2e_client, excluded_dates=["2024-02-08"])["id"]

    response = e2e_client.patch(f"/v1/meetings/{meeting_id}", json=patch)

    assert response.status_code == 200, response.text
    assert response.json()["excluded_dates"] == expected
    assert e2e_client.get(f"/v1/meetings/{meeting_id}").json()["excluded_dates"] == expected


@pytest.mark.e2e
@pytest.mark.parametrize(
    "patch",
    [
        {"end_date": "2024-02-08"},  # 제외 날짜가 마지막 날이 된다
        {"start_date": "2024-02-08"},  # 제외 날짜가 첫날이 된다
        {"end_date": "2024-02-07"},  # 제외 날짜가 기간 뒤로 나간다
        {"start_date": "2024-02-09"},  # 제외 날짜가 기간 앞으로 나간다
        {"start_date": "2024-02-09", "end_date": "2024-02-12"},
    ],
)
def test_patch_period_leaving_excluded_date_outside_is_422_and_keeps_stored(e2e_client, patch):
    meeting = _create(e2e_client, excluded_dates=["2024-02-08"])

    response = e2e_client.patch(f"/v1/meetings/{meeting['id']}", json=patch)

    assert response.status_code == 422, response.text
    assert response.json()["error_type"] == "InvalidMeetingError"
    assert e2e_client.get(f"/v1/meetings/{meeting['id']}").json() == meeting


@pytest.mark.e2e
@pytest.mark.parametrize(
    "patch",
    [
        {"excluded_dates": ["2024-02-05"]},
        {"excluded_dates": ["2024-02-11"]},
        {"excluded_dates": ["2024-02-12"]},
        {"excluded_dates": ["2024-02-06", "2024-02-06"]},
        {"excluded_dates": None},
        {"excluded_dates": ["2024-02-30"]},
    ],
)
def test_patch_invalid_excluded_dates_is_422_and_keeps_stored(e2e_client, patch):
    meeting = _create(e2e_client, excluded_dates=["2024-02-08"])

    response = e2e_client.patch(f"/v1/meetings/{meeting['id']}", json=patch)

    assert response.status_code == 422, response.text
    assert e2e_client.get(f"/v1/meetings/{meeting['id']}").json() == meeting


@pytest.mark.e2e
def test_patch_excluded_dates_keeps_answers(e2e_client):
    meeting_id = _create(e2e_client)["id"]
    participant_id = _participate(e2e_client, meeting_id)
    _put(e2e_client, meeting_id, participant_id, [
        {"start_time": "2024-02-06T09:00:00Z", "end_time": "2024-02-06T10:00:00Z"},
    ])
    before = e2e_client.get(f"/v1/meetings/{meeting_id}/availability").json()
    assert sum(cell["count"] for cell in _grid(e2e_client, meeting_id)) == 2

    assert e2e_client.patch(
        f"/v1/meetings/{meeting_id}", json={"excluded_dates": ["2024-02-06"]},
    ).status_code == 200
    assert e2e_client.get(f"/v1/meetings/{meeting_id}/availability").json() == before
    assert sum(cell["count"] for cell in _grid(e2e_client, meeting_id)) == 0

    assert e2e_client.patch(f"/v1/meetings/{meeting_id}", json={"excluded_dates": []}).status_code == 200
    assert sum(cell["count"] for cell in _grid(e2e_client, meeting_id)) == 2
