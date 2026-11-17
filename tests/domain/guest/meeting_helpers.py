"""미팅 경로 테스트의 도우미 (토큰 검증을 켠 guest_client와 실제 미팅 호스트)"""
import uuid

OWNER = "owner-1"
MEMBER = "member-1"

# UTC, 하루 09:00–11:00, 60분 칸, 5일 → 칸 10개
MEETING = {
    "title": "팀 회의",
    "description": "다음 주 회의",
    "start_date": "2099-03-02",
    "end_date": "2099-03-06",
    "timezone": "UTC",
    "mode": "hourly",
    "start_time": "09:00:00",
    "end_time": "11:00:00",
    "time_slot_minutes": 60,
}
CELL_COUNT = 10
SLOT = {"start_time": "2099-03-02T09:00:00Z", "end_time": "2099-03-02T10:00:00Z"}
SLOT_CELL_START = "2099-03-02T09:00:00+0000"


def create_meeting(client, tokens, *, owner: str = OWNER) -> str:
    """PUBLIC이고 게스트를 허용한 미팅"""
    headers = tokens.member(owner)
    response = client.post("/v1/meetings", json=MEETING, headers=headers)
    assert response.status_code == 201, response.text
    meeting_id = response.json()["id"]
    set_level(client, tokens, meeting_id, "public", owner=owner)
    set_allow_guests(client, tokens, meeting_id, True, owner=owner)
    return meeting_id


def set_level(client, tokens, meeting_id: str, level: str | None, *, owner: str = OWNER) -> None:
    """공개 범위를 바꾼다. None이면 설정을 지운다(private)"""
    url = f"/v1/visibility/meeting/{meeting_id}"
    if level is None:
        response = client.delete(url, headers=tokens.member(owner))
    else:
        body = {"level": level}
        if level == "allowed_emails":
            body["allowed_emails"] = ["someone@example.com"]
        response = client.put(url, json=body, headers=tokens.member(owner))
    assert response.status_code == 200, response.text


def set_allow_guests(client, tokens, meeting_id: str, value: bool, *, owner: str = OWNER) -> None:
    response = client.patch(f"/v1/meetings/{meeting_id}", json={"allow_guests": value}, headers=tokens.member(owner))
    assert response.status_code == 200, response.text


def participate(client, meeting_id: str, headers: dict, name: str = "회원") -> dict:
    response = client.post(f"/v1/meetings/{meeting_id}/participate", json={"display_name": name}, headers=headers)
    assert response.status_code in (200, 201), response.text
    return response.json()


def set_slots(client, meeting_id: str, participant_id: str, headers: dict, slots: list | None = None):
    return client.put(
        f"/v1/meetings/{meeting_id}/availability",
        params={"participant_id": participant_id},
        json=[SLOT] if slots is None else slots,
        headers=headers,
    )


def cell_count(result: dict) -> int:
    return next(c["count"] for c in result["availability_grid"] if c["start_time"] == SLOT_CELL_START)


def guest_routes(meeting_id: str) -> list[tuple[str, str, object]]:
    """게스트를 받는 미팅 경로 (메서드, URL, 본문)"""
    return [
        ("GET", f"/v1/meetings/{meeting_id}", None),
        ("GET", f"/v1/meetings/{meeting_id}/result", None),
        ("GET", f"/v1/meetings/{meeting_id}/availability", None),
        ("POST", f"/v1/meetings/{meeting_id}/participate", {"display_name": "참여"}),
        ("PUT", f"/v1/meetings/{meeting_id}/availability?participant_id={uuid.uuid4()}", [SLOT]),
    ]


def call(client, method: str, url: str, body, headers: dict | None = None):
    return client.request(method, url, json=body, headers=headers or {})


def without_request_values(response) -> tuple:
    """상태, content-type, 헤더 이름, error_id·timestamp·path를 뺀 본문"""
    body = response.json()
    if isinstance(body, dict):
        body = {k: v for k, v in body.items() if k not in ("error_id", "timestamp", "path")}
    return (
        response.status_code,
        response.headers.get("content-type"),
        sorted(name for name in response.headers.keys() if name not in ("content-length", "x-request-id")),
        body,
    )
