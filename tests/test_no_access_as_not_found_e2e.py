"""
접근할 수 없는 리소스는 없는 리소스와 같은 응답을 받는다

일정·Todo·타이머·미팅 단건 조회와 하위 경로, 쓰기 경로, 접근권한 API에서
접근이 거부된 기존 리소스와 임의 UUID의 응답이 상태 코드, content-type, 헤더 이름,
본문(error_id·timestamp·path 제외)까지 같다.
"""
from uuid import uuid4

import pytest

from tests.conftest import TimerCommands

DENIALS = [
    "private",
    "friends_not_friend",
    "selected_not_listed",
    "allowed_emails_mismatch",
    "blocked",
    "dormant_owner",
]

INSTANCE_START = "2024-01-02T10:00:00Z"


def _code(client) -> str:
    return client.get("/v1/users/me").json()["friend_code"]


def _befriend(requester, addressee) -> None:
    assert requester.post("/v1/friends/requests", json={"friend_code": _code(addressee)}).status_code == 201
    request_id = addressee.get("/v1/friends/requests/received").json()[-1]["id"]
    assert addressee.post(f"/v1/friends/requests/{request_id}/accept").status_code == 200


def _share(owner, resource: str, resource_id: str, body: dict) -> None:
    response = owner.put(f"/v1/visibility/{resource}/{resource_id}", json=body)
    assert response.status_code == 200, response.text


def _make_schedule(client, recurring: bool = False) -> str:
    body = {"title": "일정", "start_time": "2024-01-01T10:00:00Z", "end_time": "2024-01-01T12:00:00Z"}
    if recurring:
        body["recurrence_rule"] = "FREQ=DAILY;COUNT=5"
    response = client.post("/v1/schedules", json=body)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _make_todo(client) -> str:
    group_id = client.post("/v1/todos/groups", json={"name": "업무", "color": "#FF5733"}).json()["id"]
    response = client.post("/v1/todos", json={"title": "Todo", "todo_group_id": group_id})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _make_timer(client) -> str:
    return TimerCommands(client).create_timer(title="타이머", allocated_duration=1800)["id"]


def _make_meeting(client) -> str:
    response = client.post(
        "/v1/meetings",
        json={
            "title": "회의",
            "start_date": "2024-02-01",
            "end_date": "2024-02-07",
            "available_days": [0, 2, 4],
            "start_time": "09:00:00",
            "end_time": "18:00:00",
            "time_slot_minutes": 30,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


MAKERS = {
    "schedule": _make_schedule,
    "todo": _make_todo,
    "timer": _make_timer,
    "meeting": _make_meeting,
}


def _deny(multi_user_e2e, owner, viewer, resource: str, resource_id: str, denial: str) -> None:
    """owner의 리소스를 viewer가 접근할 수 없는 상태로 만든다"""
    viewer_sub = multi_user_e2e.get_user("viewer").sub
    if denial == "private":
        return
    if denial == "friends_not_friend":
        _share(owner, resource, resource_id, {"level": "friends"})
    elif denial == "selected_not_listed":
        other = multi_user_e2e.as_user("other")
        _befriend(owner, viewer)
        _befriend(owner, other)
        other_sub = multi_user_e2e.get_user("other").sub
        _share(owner, resource, resource_id, {"level": "selected", "allowed_user_ids": [other_sub]})
    elif denial == "allowed_emails_mismatch":
        _share(owner, resource, resource_id, {"level": "allowed_emails", "allowed_emails": ["someone@other.com"]})
    elif denial == "blocked":
        _share(owner, resource, resource_id, {"level": "public"})
        assert owner.post(f"/v1/friends/block/{viewer_sub}").status_code == 200
    elif denial == "dormant_owner":
        _share(owner, resource, resource_id, {"level": "public"})
        assert owner.post("/v1/users/me/deletion").status_code == 200
    else:
        raise AssertionError(denial)


def _normalized(response):
    body = response.json()
    for key in ("error_id", "timestamp", "path"):
        body.pop(key, None)
    return response.status_code, response.headers.get("content-type"), sorted(response.headers.keys()), body


def _assert_same_as_missing(call, path: str, resource_id: str, **kwargs) -> None:
    existing = call(path.format(id=resource_id), **kwargs)
    missing = call(path.format(id=uuid4()), **kwargs)

    assert existing.status_code == 404, existing.text
    assert _normalized(existing) == _normalized(missing)


# (리소스, HTTP 메서드, 경로, 요청 인자)
READS = [
    ("schedule", "get", "/v1/schedules/{id}", {}),
    ("schedule", "get", "/v1/schedules/{id}/timers", {}),
    ("schedule", "get", "/v1/schedules/{id}/timers/active", {}),
    ("todo", "get", "/v1/todos/{id}", {}),
    ("todo", "get", "/v1/todos/{id}/timers", {}),
    ("todo", "get", "/v1/todos/{id}/timers/active", {}),
    ("timer", "get", "/v1/timers/{id}", {}),
    ("meeting", "get", "/v1/meetings/{id}", {}),
    ("meeting", "post", "/v1/meetings/{id}/participate", {"json": {"display_name": "참여자"}}),
    ("meeting", "get", "/v1/meetings/{id}/availability", {}),
    ("meeting", "get", "/v1/meetings/{id}/result", {}),
    (
        "meeting",
        "put",
        "/v1/meetings/{id}/availability",
        {
            "params": {"participant_id": "00000000-0000-4000-8000-000000000000"},
            "json": [{"slot_date": "2024-02-05", "start_time": "09:00:00", "end_time": "12:00:00"}],
        },
    ),
]


@pytest.mark.e2e
@pytest.mark.parametrize("denial", DENIALS)
@pytest.mark.parametrize(("resource", "method", "path", "kwargs"), READS, ids=lambda v: v if isinstance(v, str) else "")
def test_denied_read_matches_missing(multi_user_e2e, denial, resource, method, path, kwargs):
    owner = multi_user_e2e.as_user("owner")
    viewer = multi_user_e2e.as_user("viewer")
    resource_id = MAKERS[resource](owner)
    _deny(multi_user_e2e, owner, viewer, resource, resource_id, denial)

    _assert_same_as_missing(getattr(viewer, method), path, resource_id, **kwargs)


@pytest.mark.e2e
@pytest.mark.parametrize("denial", DENIALS)
def test_denied_recurring_instance_read_matches_missing(multi_user_e2e, denial):
    owner = multi_user_e2e.as_user("owner")
    viewer = multi_user_e2e.as_user("viewer")
    parent_id = _make_schedule(owner, recurring=True)
    _deny(multi_user_e2e, owner, viewer, "schedule", parent_id, denial)

    _assert_same_as_missing(viewer.get, "/v1/schedules/{id}", parent_id, params={"instance_start": INSTANCE_START})


# 다른 사용자의 리소스에 대한 쓰기. 읽기가 허용된 공개 리소스도 같은 응답이다
WRITES = [
    ("schedule", "patch", "/v1/schedules/{id}", {"json": {"title": "변경"}}),
    ("schedule", "delete", "/v1/schedules/{id}", {}),
    ("schedule", "post", "/v1/schedules/{id}/todo", {}),
    ("todo", "patch", "/v1/todos/{id}", {"json": {"title": "변경"}}),
    ("todo", "delete", "/v1/todos/{id}", {}),
    ("timer", "patch", "/v1/timers/{id}", {"json": {"title": "변경"}}),
    ("timer", "patch", "/v1/timers/{id}/pause", {}),
    ("timer", "patch", "/v1/timers/{id}/resume", {}),
    ("timer", "post", "/v1/timers/{id}/stop", {}),
    ("timer", "post", "/v1/timers/{id}/cancel", {}),
    ("timer", "delete", "/v1/timers/{id}", {}),
    ("meeting", "patch", "/v1/meetings/{id}", {"json": {"title": "변경"}}),
    ("meeting", "delete", "/v1/meetings/{id}", {}),
]


@pytest.mark.e2e
@pytest.mark.parametrize("level", ["private", "public"])
@pytest.mark.parametrize(("resource", "method", "path", "kwargs"), WRITES, ids=lambda v: v if isinstance(v, str) else "")
def test_write_on_others_resource_matches_missing(multi_user_e2e, level, resource, method, path, kwargs):
    owner = multi_user_e2e.as_user("owner")
    viewer = multi_user_e2e.as_user("viewer")
    resource_id = MAKERS[resource](owner)
    if level == "public":
        _share(owner, resource, resource_id, {"level": "public"})

    _assert_same_as_missing(getattr(viewer, method), path, resource_id, **kwargs)


@pytest.mark.e2e
@pytest.mark.parametrize("level", ["private", "public"])
@pytest.mark.parametrize("method", ["patch", "delete"])
def test_recurring_instance_write_on_others_schedule_matches_missing(multi_user_e2e, level, method):
    owner = multi_user_e2e.as_user("owner")
    viewer = multi_user_e2e.as_user("viewer")
    parent_id = _make_schedule(owner, recurring=True)
    if level == "public":
        _share(owner, "schedule", parent_id, {"level": "public"})
    kwargs = {"params": {"instance_start": INSTANCE_START}}
    if method == "patch":
        kwargs["json"] = {"title": "변경"}

    _assert_same_as_missing(getattr(viewer, method), "/v1/schedules/{id}", parent_id, **kwargs)


@pytest.mark.e2e
@pytest.mark.parametrize("level", ["private", "public"])
@pytest.mark.parametrize("link", ["schedule_id", "todo_id"])
def test_timer_linked_to_others_resource_matches_missing(multi_user_e2e, level, link):
    owner = multi_user_e2e.as_user("owner")
    viewer = multi_user_e2e.as_user("viewer")
    resource = link.removesuffix("_id")
    resource_id = MAKERS[resource](owner)
    if level == "public":
        _share(owner, resource, resource_id, {"level": "public"})

    existing = viewer.post("/v1/timers", json={"title": "t", "allocated_duration": 60, link: resource_id})
    missing = viewer.post("/v1/timers", json={"title": "t", "allocated_duration": 60, link: str(uuid4())})

    assert existing.status_code == 404, existing.text
    assert _normalized(existing) == _normalized(missing)


@pytest.mark.e2e
def test_availability_for_others_participant_matches_missing_participant(multi_user_e2e):
    """접근 가능한 미팅에서 다른 사용자의 참여자 ID는 없는 참여자 ID와 같은 응답"""
    owner = multi_user_e2e.as_user("owner")
    viewer = multi_user_e2e.as_user("viewer")
    meeting_id = _make_meeting(owner)
    _share(owner, "meeting", meeting_id, {"level": "public"})
    owner_participant_id = owner.post(
        f"/v1/meetings/{meeting_id}/participate", json={"display_name": "주최자"}
    ).json()["id"]
    slots = [{"slot_date": "2024-02-05", "start_time": "09:00:00", "end_time": "12:00:00"}]

    existing = viewer.put(
        f"/v1/meetings/{meeting_id}/availability", params={"participant_id": owner_participant_id}, json=slots
    )
    missing = viewer.put(f"/v1/meetings/{meeting_id}/availability", params={"participant_id": str(uuid4())}, json=slots)

    assert existing.status_code == 404, existing.text
    assert existing.json()["error_type"] == "MeetingParticipantNotFoundError"
    assert _normalized(existing) == _normalized(missing)


@pytest.mark.e2e
@pytest.mark.parametrize("resource", ["schedule", "todo", "timer", "meeting"])
@pytest.mark.parametrize("level", ["private", "public"])
@pytest.mark.parametrize(
    ("method", "kwargs"),
    [("get", {}), ("put", {"json": {"level": "public"}}), ("delete", {})],
)
def test_visibility_api_on_others_resource_matches_missing(multi_user_e2e, resource, level, method, kwargs):
    owner = multi_user_e2e.as_user("owner")
    viewer = multi_user_e2e.as_user("viewer")
    resource_id = MAKERS[resource](owner)
    if level == "public":
        _share(owner, resource, resource_id, {"level": "public"})

    _assert_same_as_missing(getattr(viewer, method), f"/v1/visibility/{resource}/{{id}}", resource_id, **kwargs)
