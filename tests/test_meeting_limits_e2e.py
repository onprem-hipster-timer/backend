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
