"""
Meeting 입력 제한 E2E 테스트

표시 이름, 미팅 모양(기간·요일·시간 단위), 수정 후 미팅, 참여 중복, 가능 시간 개수의 규칙
"""
import pytest

BASE_MEETING = {
    "title": "입력 제한 테스트",
    "start_date": "2024-02-05",  # 월요일
    "end_date": "2024-02-09",  # 금요일
    "available_days": [0, 1, 2, 3, 4],
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
# 미팅 모양: 기간 3개월 이내, 요일 1개 이상, 시간 단위 5–1440분이면서 하루 범위 이하
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
        {"available_days": [6]},
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
        {"available_days": []},
        {"time_slot_minutes": 4},
        {"time_slot_minutes": 1441},
        {"start_time": "00:00:00", "end_time": "23:59:59", "time_slot_minutes": 1440},  # 하루 범위(24시간 미만)보다 김
        {"start_time": "09:00:00", "end_time": "10:00:00", "time_slot_minutes": 61},
        {"start_time": "10:00:00", "end_time": "10:00:00"},
        {"start_time": "10:00:00", "end_time": "09:00:00"},
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


@pytest.mark.e2e
def test_meeting_title_is_trimmed(e2e_client):
    response = e2e_client.post("/v1/meetings", json={**BASE_MEETING, "title": "  주간 회의  "})

    assert response.status_code == 201
    assert response.json()["title"] == "주간 회의"


# ============================================================
# PATCH: 저장된 값에 수정 내용을 합친 미팅이 생성 규칙을 지켜야 한다
# ============================================================

_SHAPE_FIELDS = (
    "title", "description", "start_date", "end_date", "available_days",
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
        {"start_time": "09:00:00", "end_time": "10:00:00", "time_slot_minutes": 90},
        {"time_slot_minutes": 4},
        {"time_slot_minutes": 1441},
        {"available_days": []},
        {"title": ""},
        {"title": "   "},
        {"title": "a" * 201},
        {"description": "d" * 2001},
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
        ({"title": "  새 제목  "}, {"title": "새 제목"}),
        ({"description": None}, {"description": None}),
        ({"title": None}, {}),  # null은 NOT NULL 필드를 바꾸지 않는다
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

_SLOT = {"slot_date": "2024-02-05", "start_time": "09:00:00", "end_time": "10:00:00"}


def _counts(client, meeting_id: str, slot_date: str = "2024-02-05") -> dict[str, int]:
    result = client.get(f"/v1/meetings/{meeting_id}/result").json()
    group = next(g for g in result["availability_grid"] if g["date"] == slot_date)
    return {s["time"]: s["count"] for s in group["slots"]}


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
    assert _counts(e2e_client, meeting_id)["09:00"] == 1


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
    assert _counts(owner, meeting_id)["09:00"] == 2
