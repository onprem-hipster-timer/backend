"""
공유된 반복 일정 E2E 테스트

공유된 반복 일정도 소유자의 목록과 같이 조회 범위 안의 회차로 확장된다.
"""
import pytest

OWNER = "user-a"
VIEWER = "user-c"

WEEKLY_MONDAY = {
    "title": "주간 회의",
    "description": "매주 월요일",
    "start_time": "2024-01-01T10:00:00Z",  # 월요일
    "end_time": "2024-01-01T12:00:00Z",
    "recurrence_rule": "FREQ=WEEKLY;BYDAY=MO",
    "recurrence_end": "2024-01-29T23:59:59Z",  # 1, 8, 15, 22, 29일
}


def _create(client, body: dict) -> str:
    response = client.post("/v1/schedules", json=body)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _share_publicly(client, schedule_id: str) -> None:
    response = client.put(f"/v1/visibility/schedule/{schedule_id}", json={"level": "public"})
    assert response.status_code == 200, response.text


def _list(client, start_date: str, end_date: str, scope: str) -> list[dict]:
    response = client.get(
        "/v1/schedules",
        params={"start_date": start_date, "end_date": end_date, "scope": scope},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _instances(items: list[dict], parent_id: str) -> list[dict]:
    return [s for s in items if s["parent_id"] == parent_id]


def _comparable(item: dict) -> dict:
    return {k: v for k, v in item.items() if k not in ("id", "is_shared")}


@pytest.fixture
def shared_weekly(multi_user_e2e):
    owner = multi_user_e2e.as_user(OWNER)
    viewer = multi_user_e2e.as_user(VIEWER)
    parent_id = _create(owner, WEEKLY_MONDAY)
    _share_publicly(owner, parent_id)
    return owner, viewer, parent_id


@pytest.mark.e2e
def test_viewer_sees_each_occurrence_outside_first_period(shared_weekly):
    _, viewer, parent_id = shared_weekly

    items = _list(viewer, "2024-01-08T00:00:00Z", "2024-01-21T23:59:59Z", "shared")

    instances = _instances(items, parent_id)
    assert [s["start_time"] for s in instances] == [
        "2024-01-08T10:00:00+0000",
        "2024-01-15T10:00:00+0000",
    ]
    assert parent_id not in [s["id"] for s in items]
    for instance in instances:
        assert instance["is_shared"] is True
        assert instance["owner_id"] == OWNER
        assert instance["recurrence_rule"] is None
        assert instance["title"] == "주간 회의"


@pytest.mark.e2e
def test_viewer_instances_match_owner_instances_with_exceptions(shared_weekly):
    owner, viewer, parent_id = shared_weekly
    patch = owner.patch(
        f"/v1/schedules/{parent_id}",
        params={"instance_start": "2024-01-15T10:00:00Z"},
        json={"title": "변경된 회의", "start_time": "2024-01-15T13:00:00Z", "end_time": "2024-01-15T14:00:00Z"},
    )
    assert patch.status_code == 200, patch.text
    delete = owner.delete(f"/v1/schedules/{parent_id}", params={"instance_start": "2024-01-22T10:00:00Z"})
    assert delete.status_code == 200, delete.text
    range_ = ("2024-01-08T00:00:00Z", "2024-01-28T23:59:59Z")

    viewer_instances = _instances(_list(viewer, *range_, "shared"), parent_id)
    owner_instances = _instances(_list(owner, *range_, "mine"), parent_id)

    assert [(s["title"], s["start_time"]) for s in viewer_instances] == [
        ("주간 회의", "2024-01-08T10:00:00+0000"),
        ("변경된 회의", "2024-01-15T13:00:00+0000"),
    ]
    assert [_comparable(s) for s in viewer_instances] == [_comparable(s) for s in owner_instances]
    assert all(s["is_shared"] is True for s in viewer_instances)
    assert all(s["is_shared"] is False for s in owner_instances)


@pytest.mark.e2e
def test_shared_non_recurring_schedule_unchanged(multi_user_e2e):
    owner = multi_user_e2e.as_user(OWNER)
    viewer = multi_user_e2e.as_user(VIEWER)
    schedule_id = _create(owner, {
        "title": "단일 일정", "start_time": "2024-01-08T10:00:00Z", "end_time": "2024-01-08T12:00:00Z",
    })
    _share_publicly(owner, schedule_id)

    inside = _list(viewer, "2024-01-08T00:00:00Z", "2024-01-08T23:59:59Z", "shared")
    outside = _list(viewer, "2024-01-09T00:00:00Z", "2024-01-09T23:59:59Z", "shared")

    assert [(s["id"], s["parent_id"], s["is_shared"], s["owner_id"]) for s in inside] == [
        (schedule_id, None, True, OWNER)
    ]
    assert inside[0]["visibility_level"] == "public"
    assert outside == []


@pytest.mark.e2e
@pytest.mark.parametrize(
    ("start_date", "end_date", "expected"),
    [
        ("2024-01-08T00:00:00Z", "2024-01-08T10:00:00Z", 1),  # 끝 = 회차 시작
        ("2024-01-08T00:00:00Z", "2024-01-08T09:59:59Z", 0),
        ("2024-01-08T12:00:00Z", "2024-01-08T23:59:59Z", 1),  # 시작 = 회차 끝
        ("2024-01-08T12:00:01Z", "2024-01-08T23:59:59Z", 0),
        ("2024-01-29T00:00:00Z", "2024-02-29T23:59:59Z", 1),  # 마지막 회차 이후는 없음
    ],
)
def test_shared_range_boundaries_match_owner(shared_weekly, start_date, end_date, expected):
    owner, viewer, parent_id = shared_weekly

    viewer_count = len(_instances(_list(viewer, start_date, end_date, "shared"), parent_id))
    owner_count = len(_instances(_list(owner, start_date, end_date, "mine"), parent_id))

    assert viewer_count == expected
    assert owner_count == expected


@pytest.mark.e2e
def test_scope_mine_excludes_shared_instances(shared_weekly):
    _, viewer, parent_id = shared_weekly

    items = _list(viewer, "2024-01-01T00:00:00Z", "2024-01-31T23:59:59Z", "mine")

    assert _instances(items, parent_id) == []
    assert parent_id not in [s["id"] for s in items]


@pytest.mark.e2e
def test_scope_all_returns_own_and_shared_instances_once(shared_weekly):
    _, viewer, parent_id = shared_weekly
    own_parent_id = _create(viewer, {**WEEKLY_MONDAY, "title": "내 회의"})

    items = _list(viewer, "2024-01-08T00:00:00Z", "2024-01-21T23:59:59Z", "all")

    shared = _instances(items, parent_id)
    own = _instances(items, own_parent_id)
    assert len(shared) == 2 and all(s["is_shared"] for s in shared)
    assert len(own) == 2 and not any(s["is_shared"] for s in own)
    assert len(items) == 4
    assert len({(s["parent_id"], s["start_time"]) for s in items}) == 4
    assert len({s["id"] for s in items}) == 4


@pytest.mark.e2e
def test_shared_instances_disappear_when_visibility_removed(shared_weekly):
    owner, viewer, parent_id = shared_weekly
    range_ = ("2024-01-08T00:00:00Z", "2024-01-21T23:59:59Z")
    assert len(_instances(_list(viewer, *range_, "shared"), parent_id)) == 2

    removed = owner.delete(f"/v1/visibility/schedule/{parent_id}")
    assert removed.status_code == 200, removed.text

    assert _list(viewer, *range_, "shared") == []
    assert _list(viewer, *range_, "all") == []
    read = viewer.get(f"/v1/schedules/{parent_id}", params={"instance_start": "2024-01-08T10:00:00Z"})
    assert read.status_code == 403


@pytest.mark.e2e
def test_private_recurring_schedule_is_not_expanded_for_others(multi_user_e2e):
    owner = multi_user_e2e.as_user(OWNER)
    viewer = multi_user_e2e.as_user(VIEWER)
    _create(owner, WEEKLY_MONDAY)

    assert _list(viewer, "2024-01-01T00:00:00Z", "2024-01-31T23:59:59Z", "shared") == []


@pytest.mark.e2e
def test_viewer_reads_shared_instance_by_instance_start(shared_weekly):
    owner, viewer, parent_id = shared_weekly
    owner.patch(
        f"/v1/schedules/{parent_id}",
        params={"instance_start": "2024-01-15T10:00:00Z"},
        json={"title": "변경된 회의"},
    )

    response = viewer.get(f"/v1/schedules/{parent_id}", params={"instance_start": "2024-01-15T10:00:00Z"})

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["parent_id"] == parent_id
    assert data["title"] == "변경된 회의"
    assert data["is_shared"] is True
    assert data["owner_id"] == OWNER
    listed = _instances(_list(viewer, "2024-01-15T00:00:00Z", "2024-01-15T23:59:59Z", "shared"), parent_id)
    assert [_comparable(data)] == [_comparable(s) for s in listed]


@pytest.mark.e2e
def test_viewer_cannot_update_or_delete_shared_instance(shared_weekly):
    owner, viewer, parent_id = shared_weekly
    params = {"instance_start": "2024-01-15T10:00:00Z"}

    parent_patch = viewer.patch(f"/v1/schedules/{parent_id}", json={"title": "남의 수정"})
    instance_patch = viewer.patch(f"/v1/schedules/{parent_id}", params=params, json={"title": "남의 수정"})
    instance_delete = viewer.delete(f"/v1/schedules/{parent_id}", params=params)

    assert parent_patch.status_code == 404
    assert instance_patch.status_code == parent_patch.status_code
    assert instance_delete.status_code == parent_patch.status_code
    owner_instances = _instances(
        _list(owner, "2024-01-15T00:00:00Z", "2024-01-15T23:59:59Z", "mine"), parent_id
    )
    assert [s["title"] for s in owner_instances] == ["주간 회의"]


@pytest.mark.e2e
def test_viewer_reads_moved_shared_instance_by_listed_instance_start(shared_weekly):
    owner, viewer, parent_id = shared_weekly
    moved = owner.patch(
        f"/v1/schedules/{parent_id}",
        params={"instance_start": "2024-01-08T10:00:00Z"},
        json={"start_time": "2024-01-09T15:00:00Z", "end_time": "2024-01-09T16:00:00Z"},
    )
    assert moved.status_code == 200, moved.text

    listed = _instances(_list(viewer, "2024-01-08T00:00:00Z", "2024-01-10T23:59:59Z", "shared"), parent_id)

    assert [(s["instance_start"], s["start_time"]) for s in listed] == [
        ("2024-01-08T10:00:00+0000", "2024-01-09T15:00:00+0000")
    ]
    read = viewer.get(f"/v1/schedules/{parent_id}", params={"instance_start": listed[0]["instance_start"]})
    assert read.status_code == 200, read.text
    assert read.json()["is_shared"] is True
    assert _comparable(read.json()) == _comparable(listed[0])
