"""
Meeting 입력 제한 E2E 테스트

표시 이름, 미팅 모양(기간·제외 날짜·시간 단위), 수정 후 미팅, 참여 중복, 가능 시간 개수의 규칙
"""
from datetime import date, datetime, timedelta

import pytest

BASE_MEETING = {
    "title": "입력 제한 테스트",
    "start_date": "2024-02-05",  # 월요일
    "end_date": "2024-02-09",  # 금요일
    "timezone": "UTC",
    "mode": "hourly",
    "start_time": "09:00:00",
    "end_time": "18:00:00",
    "time_slot_minutes": 30,
}


def _create_meeting(client, **overrides):
    response = client.post("/v1/meetings", json={**BASE_MEETING, **overrides})
    assert response.status_code == 201, response.text
    return response.json()["id"]


# ============================================================
# 표시 이름: 앞뒤 공백을 뺀 1–50자, 제어 문자 불가
# ============================================================

@pytest.mark.e2e
@pytest.mark.parametrize(
    "display_name, stored",
    [
        ("가", "가"),
        ("a" * 50, "a" * 50),
        ("  참여자  ", "참여자"),
        (" " + "b" * 50 + " ", "b" * 50),
        ("🙂 민수", "🙂 민수"),
        ("👨‍👩‍👧", "👨‍👩‍👧"),
    ],
)
def test_display_name_accepted_and_trimmed(e2e_client, display_name, stored):
    meeting_id = _create_meeting(e2e_client)

    response = e2e_client.post(
        f"/v1/meetings/{meeting_id}/participate", json={"display_name": display_name}
    )

    assert response.status_code == 201, response.text
    assert response.json()["display_name"] == stored


@pytest.mark.e2e
@pytest.mark.parametrize(
    "display_name",
    ["", "   ", "\t\n", "a" * 51, "참여\x00자", "참여\n자", "참여\x7f자", "참여\x85자"],
)
def test_display_name_rejected(e2e_client, display_name):
    meeting_id = _create_meeting(e2e_client)

    response = e2e_client.post(
        f"/v1/meetings/{meeting_id}/participate", json={"display_name": display_name}
    )

    assert response.status_code == 422, response.text
    assert e2e_client.get(f"/v1/meetings/{meeting_id}/availability").json() == []


# ============================================================
# 미팅 모양: 기간 3개월 이내, 제외 날짜는 기간 안쪽, 시간 단위 5–1440분이면서 하루 범위 이하
# ============================================================

@pytest.mark.e2e
@pytest.mark.parametrize(
    "overrides",
    [
        {"start_date": "2024-02-05", "end_date": "2024-05-05"},  # 정확히 3개월
        {"start_date": "2024-11-30", "end_date": "2025-02-28"},  # 말일 시작: 3개월 뒤 같은 날이 없으면 그 달 말일
        {"start_date": "2024-02-05", "end_date": "2024-02-05"},  # 하루
        {"time_slot_minutes": 5},
        {"start_time": "09:00:00", "end_time": "10:00:00", "time_slot_minutes": 60},  # 단위 = 하루 범위
        {"start_time": "00:00:00", "end_time": "23:59:00", "time_slot_minutes": 1439},  # 하루 전체를 한 칸으로
        {"start_time": "00:00:00", "end_time": "00:00:00", "time_slot_minutes": 1440},  # 00:00 끝 = 하루의 끝
        {"start_time": "00:00:00", "end_time": "00:00:00", "time_slot_minutes": 30},
        {"start_time": "22:00:00", "end_time": "00:00:00", "time_slot_minutes": 120},
        {"excluded_dates": ["2024-02-06", "2024-02-08"]},
        {"title": "a" * 200},
        {"description": "d" * 2000},
        {"description": None},
    ],
)
def test_meeting_shape_accepted(e2e_client, overrides):
    response = e2e_client.post("/v1/meetings", json={**BASE_MEETING, **overrides})

    assert response.status_code == 201, response.text


@pytest.mark.e2e
@pytest.mark.parametrize(
    "overrides",
    [
        {"start_date": "2024-02-05", "end_date": "2024-05-06"},  # 3개월 + 1일
        {"start_date": "2024-11-30", "end_date": "2025-03-01"},
        {"start_date": "2024-02-05", "end_date": "2024-02-04"},
        {"excluded_dates": ["2024-02-05"]},
        {"time_slot_minutes": 4},
        {"time_slot_minutes": 1441},
        {"start_time": "00:00:00", "end_time": "23:59:59", "time_slot_minutes": 1440},  # 하루 범위(24시간 미만)보다 김
        {"start_time": "09:00:00", "end_time": "10:00:00", "time_slot_minutes": 61},
        {"start_time": "10:00:00", "end_time": "10:00:00"},
        {"start_time": "10:00:00", "end_time": "09:00:00"},
        {"start_time": "10:00:00", "end_time": "00:30:00"},  # 00:00이 아닌 끝은 시작보다 뒤여야 한다
        {"start_time": "22:00:00", "end_time": "00:00:00", "time_slot_minutes": 121},
        {"title": ""},
        {"title": "   "},
        {"title": "a" * 201},
        {"description": "d" * 2001},
    ],
)
def test_meeting_shape_rejected(e2e_client, overrides):
    response = e2e_client.post("/v1/meetings", json={**BASE_MEETING, **overrides})

    assert response.status_code == 422, response.text
    assert e2e_client.get("/v1/meetings").json() == []


# ============================================================
# 시간대: IANA 이름만, 생성 때 필수
# ============================================================

@pytest.mark.e2e
@pytest.mark.parametrize("name", ["Asia/Seoul", "America/New_York", "UTC"])
def test_meeting_timezone_accepted_and_returned(e2e_client, name):
    response = e2e_client.post("/v1/meetings", json={**BASE_MEETING, "timezone": name})

    assert response.status_code == 201, response.text
    meeting_id = response.json()["id"]
    assert response.json()["timezone"] == name
    assert e2e_client.get(f"/v1/meetings/{meeting_id}").json()["timezone"] == name


@pytest.mark.e2e
@pytest.mark.parametrize("name", ["Mars/Olympus", "+09:00", "-05:00", "KST+9", "", "Asia/../UTC", None])
def test_meeting_timezone_rejected(e2e_client, name):
    response = e2e_client.post("/v1/meetings", json={**BASE_MEETING, "timezone": name})

    assert response.status_code == 422, response.text
    assert e2e_client.get("/v1/meetings").json() == []


@pytest.mark.e2e
def test_meeting_timezone_required(e2e_client):
    body = {key: value for key, value in BASE_MEETING.items() if key != "timezone"}

    response = e2e_client.post("/v1/meetings", json=body)

    assert response.status_code == 422, response.text


@pytest.mark.e2e
def test_meeting_title_is_trimmed(e2e_client):
    response = e2e_client.post("/v1/meetings", json={**BASE_MEETING, "title": "  주간 회의  "})

    assert response.status_code == 201
    assert response.json()["title"] == "주간 회의"


# ============================================================
# PATCH: 저장된 값에 수정 내용을 합친 미팅이 생성 규칙을 지켜야 한다
# ============================================================

_SHAPE_FIELDS = (
    "title", "description", "start_date", "end_date", "excluded_dates", "timezone", "mode",
    "start_time", "end_time", "time_slot_minutes",
)


def _shape(meeting: dict) -> dict:
    return {key: meeting[key] for key in _SHAPE_FIELDS}


@pytest.mark.e2e
@pytest.mark.parametrize(
    "patch",
    [
        {"start_time": "18:00:00"},  # 저장된 end_time과 같음
        {"start_time": "19:00:00"},
        {"end_time": "09:00:00"},  # 저장된 start_time과 같음
        {"end_time": "08:00:00"},
        {"start_time": "12:00:00", "end_time": "11:00:00"},
        {"start_date": "2024-02-10"},  # 저장된 end_date보다 뒤
        {"end_date": "2024-02-04"},  # 저장된 start_date보다 앞
        {"start_date": "2024-02-10", "end_date": "2024-02-09"},
        {"end_date": "2024-05-06"},  # 저장된 start_date + 3개월 + 1일
        {"start_date": "2023-11-08"},  # 저장된 end_date까지 3개월 초과
        {"start_date": "2024-01-01", "end_date": "2024-04-02"},
        {"time_slot_minutes": 541},  # 저장된 하루 범위(540분)보다 김
        {"start_time": "17:45:00"},  # 하루 범위가 저장된 단위(30분)보다 짧아짐
        {"end_time": "09:20:00"},
        {"end_time": "00:30:00"},
        {"start_time": "23:45:00", "end_time": "00:00:00"},  # 하루 범위 15분 < 저장된 단위 30분
        {"start_time": "09:00:00", "end_time": "10:00:00", "time_slot_minutes": 90},
        {"time_slot_minutes": 4},
        {"time_slot_minutes": 1441},
        {"excluded_dates": ["2024-02-09"]},
        {"title": ""},
        {"title": "   "},
        {"title": "a" * 201},
        {"description": "d" * 2001},
        {"timezone": "Mars/Olympus"},
        {"timezone": "+09:00"},
        {"timezone": None},
    ],
)
def test_patch_making_invalid_meeting_is_422_and_keeps_stored(e2e_client, patch):
    meeting_id = _create_meeting(e2e_client)
    before = _shape(e2e_client.get(f"/v1/meetings/{meeting_id}").json())

    response = e2e_client.patch(f"/v1/meetings/{meeting_id}", json=patch)

    assert response.status_code == 422, response.text
    assert _shape(e2e_client.get(f"/v1/meetings/{meeting_id}").json()) == before


@pytest.mark.e2e
@pytest.mark.parametrize(
    "patch, expected",
    [
        ({"start_time": "19:00:00", "end_time": "20:00:00"}, {"start_time": "19:00:00", "end_time": "20:00:00"}),
        ({"end_date": "2024-05-05"}, {"end_date": "2024-05-05"}),
        ({"start_date": "2024-02-09"}, {"start_date": "2024-02-09"}),
        ({"time_slot_minutes": 540}, {"time_slot_minutes": 540}),
        ({"end_time": "00:00:00"}, {"end_time": "00:00:00"}),
        ({"start_time": "00:00:00", "end_time": "00:00:00", "time_slot_minutes": 1440},
         {"start_time": "00:00:00", "end_time": "00:00:00", "time_slot_minutes": 1440}),
        ({"title": "  새 제목  "}, {"title": "새 제목"}),
        ({"description": None}, {"description": None}),
        ({"title": None}, {}),  # null은 NOT NULL 필드를 바꾸지 않는다
        ({"timezone": "Asia/Seoul"}, {"timezone": "Asia/Seoul"}),
    ],
)
def test_patch_making_valid_meeting_is_applied(e2e_client, patch, expected):
    meeting_id = _create_meeting(e2e_client, description="설명")
    before = _shape(e2e_client.get(f"/v1/meetings/{meeting_id}").json())

    response = e2e_client.patch(f"/v1/meetings/{meeting_id}", json=patch)

    assert response.status_code == 200, response.text
    assert _shape(response.json()) == {**before, **expected}
    assert _shape(e2e_client.get(f"/v1/meetings/{meeting_id}").json()) == {**before, **expected}


# ============================================================
# 참여: 미팅마다 사용자당 참여자 한 명
# ============================================================

_SLOT = {"start_time": "2024-02-05T09:00:00Z", "end_time": "2024-02-05T10:00:00Z"}


def _counts(client, meeting_id: str) -> dict[str, int]:
    """칸 시작 시각 → 인원 수"""
    result = client.get(f"/v1/meetings/{meeting_id}/result").json()
    return {cell["start_time"]: cell["count"] for cell in result["availability_grid"]}


@pytest.mark.e2e
def test_repeat_participation_returns_same_participant_and_renames(e2e_client):
    meeting_id = _create_meeting(e2e_client)

    first = e2e_client.post(f"/v1/meetings/{meeting_id}/participate", json={"display_name": "처음"})
    assert first.status_code == 201
    participant_id = first.json()["id"]
    assert e2e_client.put(
        f"/v1/meetings/{meeting_id}/availability", params={"participant_id": participant_id}, json=[_SLOT],
    ).status_code == 200

    again = e2e_client.post(f"/v1/meetings/{meeting_id}/participate", json={"display_name": " 바꾼 이름 "})

    assert again.status_code == 200, again.text
    assert again.json()["id"] == participant_id
    assert again.json()["display_name"] == "바꾼 이름"
    assert again.json()["created_at"] == first.json()["created_at"]
    availability = e2e_client.get(f"/v1/meetings/{meeting_id}/availability").json()
    assert [a["participant"]["id"] for a in availability] == [participant_id]
    assert availability[0]["participant"]["display_name"] == "바꾼 이름"
    assert len(availability[0]["time_slots"]) == 1  # 이름을 바꿔도 가능 시간은 그대로
    assert _counts(e2e_client, meeting_id)["2024-02-05T09:00:00+0000"] == 1


@pytest.mark.e2e
def test_repeat_participation_with_same_name_is_200(e2e_client):
    meeting_id = _create_meeting(e2e_client)
    first = e2e_client.post(f"/v1/meetings/{meeting_id}/participate", json={"display_name": "같은 이름"})

    again = e2e_client.post(f"/v1/meetings/{meeting_id}/participate", json={"display_name": "같은 이름"})

    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json()["id"] == first.json()["id"]
    assert len(e2e_client.get(f"/v1/meetings/{meeting_id}/availability").json()) == 1


@pytest.mark.e2e
def test_invalid_name_on_repeat_participation_keeps_existing_name(e2e_client):
    meeting_id = _create_meeting(e2e_client)
    e2e_client.post(f"/v1/meetings/{meeting_id}/participate", json={"display_name": "원래 이름"})

    response = e2e_client.post(f"/v1/meetings/{meeting_id}/participate", json={"display_name": "  "})

    assert response.status_code == 422
    availability = e2e_client.get(f"/v1/meetings/{meeting_id}/availability").json()
    assert [a["participant"]["display_name"] for a in availability] == ["원래 이름"]


@pytest.mark.e2e
def test_two_users_are_two_participants(multi_user_e2e):
    owner = multi_user_e2e.as_user("owner")
    member = multi_user_e2e.as_user("member")
    meeting_id = _create_meeting(owner)
    owner.put(f"/v1/visibility/meeting/{meeting_id}", json={"level": "public"})

    ids = []
    for client, name in ((owner, "주최자"), (member, "참여자"), (member, "참여자")):
        response = client.post(f"/v1/meetings/{meeting_id}/participate", json={"display_name": name})
        assert response.status_code in (200, 201), response.text
        ids.append(response.json()["id"])
        client.put(
            f"/v1/meetings/{meeting_id}/availability", params={"participant_id": ids[-1]}, json=[_SLOT],
        )

    assert ids[0] != ids[1]
    assert ids[1] == ids[2]
    availability = owner.get(f"/v1/meetings/{meeting_id}/availability").json()
    assert sorted(a["participant"]["user_id"] for a in availability) == ["member", "owner"]
    assert _counts(owner, meeting_id)["2024-02-05T09:00:00+0000"] == 2


# ============================================================
# 가능 시간: 한 요청의 슬롯 수는 미팅의 칸 수까지
# ============================================================

def _grid_slots(dates: list[str], start_hour: int = 9, cells: int = 18, minutes: int = 30) -> list[dict]:
    """날짜마다 start_hour(UTC)부터 minutes 단위 칸 cells개"""
    slots = []
    for slot_date in dates:
        for i in range(cells):
            start = start_hour * 60 + i * minutes
            end = start + minutes
            slots.append({
                "start_time": f"{slot_date}T{start // 60:02d}:{start % 60:02d}:00Z",
                "end_time": f"{slot_date}T{end // 60:02d}:{end % 60:02d}:00Z",
            })
    return slots


def _as_response(slot: dict) -> tuple[str, str]:
    return slot["start_time"].replace("Z", "+0000"), slot["end_time"].replace("Z", "+0000")


_WEEK = ["2024-02-05", "2024-02-06", "2024-02-07", "2024-02-08", "2024-02-09"]


def _participate(client, meeting_id: str) -> str:
    response = client.post(f"/v1/meetings/{meeting_id}/participate", json={"display_name": "참여자"})
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


def _put_slots(client, meeting_id: str, participant_id: str, slots: list[dict]):
    return client.put(
        f"/v1/meetings/{meeting_id}/availability", params={"participant_id": participant_id}, json=slots,
    )


def _stored_slots(client, meeting_id: str) -> list[tuple]:
    availability = client.get(f"/v1/meetings/{meeting_id}/availability").json()
    return sorted(
        (s["start_time"], s["end_time"])
        for a in availability for s in a["time_slots"]
    )


@pytest.mark.e2e
def test_slots_up_to_meeting_cell_count_accepted(e2e_client):
    meeting_id = _create_meeting(e2e_client)  # 5일 x 09:00–18:00 / 30분 = 90칸
    participant_id = _participate(e2e_client, meeting_id)

    response = _put_slots(e2e_client, meeting_id, participant_id, _grid_slots(_WEEK))

    assert response.status_code == 200, response.text
    assert len(response.json()) == 90
    assert len(_stored_slots(e2e_client, meeting_id)) == 90


@pytest.mark.e2e
def test_slots_over_meeting_cell_count_rejected_and_stored_kept(e2e_client):
    meeting_id = _create_meeting(e2e_client)
    participant_id = _participate(e2e_client, meeting_id)
    assert _put_slots(e2e_client, meeting_id, participant_id, [_grid_slots(_WEEK)[0]]).status_code == 200
    before = _stored_slots(e2e_client, meeting_id)
    over = _grid_slots(_WEEK) + [
        {"start_time": "2024-02-05T18:00:00Z", "end_time": "2024-02-05T18:30:00Z"},
    ]

    response = _put_slots(e2e_client, meeting_id, participant_id, over)

    assert response.status_code == 422, response.text
    assert _stored_slots(e2e_client, meeting_id) == before


@pytest.mark.e2e
@pytest.mark.parametrize(
    "overrides, cell_count",
    [
        # 하루 x 60분 / 25분 = 2.4 → 3
        ({"start_date": "2024-02-05", "end_date": "2024-02-05", "start_time": "09:00:00",
          "end_time": "10:00:00", "time_slot_minutes": 25}, 3),
        # 이틀 x 60분 / 25분 = 4.8 → 5
        ({"start_date": "2024-02-05", "end_date": "2024-02-06", "start_time": "09:00:00",
          "end_time": "10:00:00", "time_slot_minutes": 25}, 5),
        # 기간 7일 중 제외 5일: 2일 x 540분 / 30분 = 36
        ({"start_date": "2024-02-05", "end_date": "2024-02-11",
          "excluded_dates": ["2024-02-06", "2024-02-07", "2024-02-08", "2024-02-09", "2024-02-10"]}, 36),
        # 하루 전체(00:00–00:00) / 30분 = 48
        ({"start_date": "2024-02-05", "end_date": "2024-02-05", "start_time": "00:00:00",
          "end_time": "00:00:00"}, 48),
        # 22:00–24:00 이틀 / 30분 = 8
        ({"start_date": "2024-02-05", "end_date": "2024-02-06", "start_time": "22:00:00",
          "end_time": "00:00:00"}, 8),
    ],
)
def test_slot_cap_is_meeting_cell_count(e2e_client, overrides, cell_count):
    meeting_id = _create_meeting(e2e_client, **overrides)
    participant_id = _participate(e2e_client, meeting_id)
    first = datetime(2024, 3, 1)
    slots = [
        {"start_time": (first + timedelta(minutes=i)).isoformat() + "Z",
         "end_time": (first + timedelta(minutes=i + 1)).isoformat() + "Z"}
        for i in range(cell_count + 1)
    ]

    assert _put_slots(e2e_client, meeting_id, participant_id, slots[:cell_count]).status_code == 200
    assert _put_slots(e2e_client, meeting_id, participant_id, slots).status_code == 422


@pytest.mark.e2e
def test_duplicate_slots_are_stored_as_sent_and_count_toward_cap(e2e_client):
    meeting_id = _create_meeting(e2e_client, start_date="2024-02-05", end_date="2024-02-05",
                                 start_time="09:00:00", end_time="10:00:00", time_slot_minutes=30)  # 2칸
    participant_id = _participate(e2e_client, meeting_id)
    slot = _grid_slots(_WEEK)[0]

    assert _put_slots(e2e_client, meeting_id, participant_id, [slot, slot]).status_code == 200
    assert len(_stored_slots(e2e_client, meeting_id)) == 2
    assert _put_slots(e2e_client, meeting_id, participant_id, [slot, slot, slot]).status_code == 422


@pytest.mark.e2e
@pytest.mark.parametrize(
    "overrides, slot_date",
    [
        # 날짜만 고르는 미팅: 하루 전체(00:00–00:00)를 한 칸으로
        ({"start_date": "2024-02-05", "end_date": "2024-05-05",
          "start_time": "00:00:00", "end_time": "00:00:00", "time_slot_minutes": 1440}, "2024-05-05"),
        # 요일만 고르는 미팅: 7일 기간, 하루 전체를 한 칸으로
        ({"start_date": "2024-02-05", "end_date": "2024-02-11",
          "start_time": "00:00:00", "end_time": "00:00:00", "time_slot_minutes": 1440}, "2024-02-11"),
    ],
)
def test_whole_day_slot_accepted_and_counted(e2e_client, overrides, slot_date):
    meeting_id = _create_meeting(e2e_client, **overrides)
    participant_id = _participate(e2e_client, meeting_id)
    next_day = (date.fromisoformat(slot_date) + timedelta(days=1)).isoformat()

    response = _put_slots(e2e_client, meeting_id, participant_id, [
        {"start_time": f"{slot_date}T00:00:00Z", "end_time": f"{next_day}T00:00:00Z"},
    ])

    assert response.status_code == 200, response.text
    result = e2e_client.get(f"/v1/meetings/{meeting_id}/result").json()
    cell = next(c for c in result["availability_grid"] if c["start_time"] == f"{slot_date}T00:00:00+0000")
    assert cell == {
        "start_time": f"{slot_date}T00:00:00+0000", "end_time": f"{next_day}T00:00:00+0000", "count": 1,
    }


@pytest.mark.e2e
def test_out_of_range_slots_accepted_but_not_counted(e2e_client):
    meeting_id = _create_meeting(e2e_client)
    participant_id = _participate(e2e_client, meeting_id)
    outside = [
        {"start_time": "2024-02-10T09:00:00Z", "end_time": "2024-02-10T10:00:00Z"},  # 기간 밖(토)
        {"start_time": "2024-02-05T06:00:00Z", "end_time": "2024-02-05T07:00:00Z"},  # 하루 범위 밖
        {"start_time": "2024-02-05T09:10:00Z", "end_time": "2024-02-05T09:20:00Z"},  # 칸에 맞지 않음
    ]

    response = _put_slots(e2e_client, meeting_id, participant_id, outside)

    assert response.status_code == 200, response.text
    assert len(_stored_slots(e2e_client, meeting_id)) == 3
    result = e2e_client.get(f"/v1/meetings/{meeting_id}/result").json()
    assert all(cell["count"] == 0 for cell in result["availability_grid"])


@pytest.mark.e2e
def test_put_replaces_all_slots(e2e_client):
    meeting_id = _create_meeting(e2e_client)
    participant_id = _participate(e2e_client, meeting_id)
    grid = _grid_slots(_WEEK)

    _put_slots(e2e_client, meeting_id, participant_id, grid[:5])
    _put_slots(e2e_client, meeting_id, participant_id, grid[5:7])
    assert _stored_slots(e2e_client, meeting_id) == sorted(_as_response(s) for s in grid[5:7])

    assert _put_slots(e2e_client, meeting_id, participant_id, []).json() == []
    assert _stored_slots(e2e_client, meeting_id) == []
