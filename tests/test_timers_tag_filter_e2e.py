"""
타이머 목록 태그 필터 E2E 테스트 (GET /v1/timers의 tag_ids, tag_match)

필터는 타이머 자신의 태그 + 연결된 Schedule의 태그 + 연결된 Todo의 태그로 매칭한다.
"""
from uuid import uuid4

import pytest

from tests.conftest import TimerCommands


def _tag(client, name):
    group_id = client.post("/v1/tags/groups", json={"name": f"{name} 그룹", "color": "#FF5733"}).json()["id"]
    response = client.post("/v1/tags", json={"name": name, "color": "#00FF00", "group_id": group_id})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _schedule(client, tag_ids):
    response = client.post(
        "/v1/schedules",
        json={
            "title": "일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
            "tag_ids": tag_ids,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _todo(client, tag_ids):
    response = client.post("/v1/todos", json={"title": "할 일", "tag_ids": tag_ids})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _ids(client, **params):
    response = client.get("/v1/timers", params=params)
    assert response.status_code == 200, response.text
    return {t["id"] for t in response.json()}


@pytest.fixture
def world(e2e_client):
    """
    태그 own, sched, todo와 각 태그 출처별 타이머

    - own_timer: 자기 태그 own (독립 타이머)
    - schedule_timer: 연결된 일정의 태그 sched
    - todo_timer: 연결된 Todo(일정 없음)의 태그 todo
    - both_linked_timer: 태그 없는 일정 + 태그 todo인 Todo에 함께 연결
    - mixed_timer: 자기 태그 own + 연결된 일정의 태그 sched
    - untagged_timer: 태그 없는 독립 타이머
    """
    timers = TimerCommands(e2e_client)
    own = _tag(e2e_client, "own")
    sched = _tag(e2e_client, "sched")
    todo = _tag(e2e_client, "todo")
    sched_id = _schedule(e2e_client, [sched])
    return {
        "own": own,
        "sched": sched,
        "todo": todo,
        "own_timer": timers.create_timer(tag_ids=[own])["id"],
        "schedule_timer": timers.create_timer(schedule_id=sched_id)["id"],
        "todo_timer": timers.create_timer(todo_id=_todo(e2e_client, [todo]))["id"],
        "both_linked_timer": timers.create_timer(
            schedule_id=_schedule(e2e_client, []), todo_id=_todo(e2e_client, [todo])
        )["id"],
        "mixed_timer": timers.create_timer(schedule_id=sched_id, tag_ids=[own])["id"],
        "untagged_timer": timers.create_timer()["id"],
    }


@pytest.mark.e2e
def test_own_tag_matches(e2e_client, world):
    assert _ids(e2e_client, tag_ids=[world["own"]]) == {world["own_timer"], world["mixed_timer"]}


@pytest.mark.e2e
def test_tag_inherited_from_schedule_matches(e2e_client, world):
    assert _ids(e2e_client, tag_ids=[world["sched"]]) == {world["schedule_timer"], world["mixed_timer"]}


@pytest.mark.e2e
def test_tag_inherited_from_todo_matches(e2e_client, world):
    assert _ids(e2e_client, tag_ids=[world["todo"]]) == {world["todo_timer"], world["both_linked_timer"]}


@pytest.mark.e2e
def test_any_matches_one_of_own_or_inherited(e2e_client, world):
    result = _ids(e2e_client, tag_ids=[world["own"], world["sched"]], tag_match="any")

    assert result == {world["own_timer"], world["schedule_timer"], world["mixed_timer"]}
    assert world["untagged_timer"] not in result


@pytest.mark.e2e
def test_all_needs_own_and_inherited_together(e2e_client, world):
    expected = {world["mixed_timer"]}

    assert _ids(e2e_client, tag_ids=[world["own"], world["sched"]], tag_match="all") == expected
    assert _ids(e2e_client, tag_ids=[world["own"], world["sched"]]) == expected


@pytest.mark.e2e
def test_repeated_tag_id_counts_once(e2e_client, world):
    result = _ids(e2e_client, tag_ids=[world["own"], world["own"]], tag_match="all")

    assert result == {world["own_timer"], world["mixed_timer"]}


@pytest.mark.e2e
def test_without_tag_ids_list_is_unchanged(e2e_client, world):
    everything = _ids(e2e_client)

    assert world["untagged_timer"] in everything
    assert _ids(e2e_client, tag_match="any") == everything
    assert _ids(e2e_client, tag_match="all") == everything


@pytest.mark.e2e
@pytest.mark.parametrize("tag_match", ["all", "any"])
def test_unknown_tag_id_matches_nothing(e2e_client, world, tag_match):
    assert _ids(e2e_client, tag_ids=[str(uuid4())], tag_match=tag_match) == set()


@pytest.mark.e2e
def test_combines_with_status(e2e_client, world):
    timers = TimerCommands(e2e_client)
    timers.pause_timer(world["mixed_timer"])
    timers.pause_timer(world["untagged_timer"])

    result = _ids(e2e_client, tag_ids=[world["own"]], status=["PAUSED"])

    assert result == {world["mixed_timer"]}


@pytest.mark.e2e
def test_combines_with_type(e2e_client, world):
    any_tag = {"tag_ids": [world["own"], world["sched"], world["todo"]], "tag_match": "any"}

    assert _ids(e2e_client, type="independent", **any_tag) == {world["own_timer"]}
    assert _ids(e2e_client, type="schedule", **any_tag) == {
        world["schedule_timer"], world["both_linked_timer"], world["mixed_timer"]
    }


@pytest.mark.e2e
@pytest.mark.parametrize("tag_include_mode", ["none", "timer_only", "inherit_from_schedule"])
def test_result_does_not_depend_on_tag_include_mode(e2e_client, world, tag_include_mode):
    result = _ids(e2e_client, tag_ids=[world["sched"]], tag_include_mode=tag_include_mode)

    assert result == {world["schedule_timer"], world["mixed_timer"]}


@pytest.mark.e2e
def test_invalid_tag_match_is_rejected(e2e_client, world):
    response = e2e_client.get("/v1/timers", params={"tag_ids": [world["own"]], "tag_match": "some"})

    assert response.status_code == 422


@pytest.mark.e2e
def test_invalid_tag_id_is_rejected(e2e_client):
    response = e2e_client.get("/v1/timers", params={"tag_ids": ["not-a-uuid"]})

    assert response.status_code == 422


@pytest.mark.e2e
@pytest.mark.parametrize("tag_match", ["all", "any"])
def test_other_users_tag_does_not_match_own_timers(multi_user_e2e, tag_match):
    client_a = multi_user_e2e.as_user("user-a")
    client_b = multi_user_e2e.as_user("user-b")
    tag_a = _tag(client_a, "a")
    tag_b = _tag(client_b, "b")
    TimerCommands(client_a).create_timer(tag_ids=[tag_a])

    assert _ids(client_a, tag_ids=[tag_b], tag_match=tag_match) == set()


@pytest.mark.e2e
def test_shared_timers_are_filtered_by_owner_tags(multi_user_e2e):
    client_a = multi_user_e2e.as_user("user-a")
    client_b = multi_user_e2e.as_user("user-b")
    timers_a = TimerCommands(client_a)
    own = _tag(client_a, "own")
    sched = _tag(client_a, "sched")
    tag_b = _tag(client_b, "b")
    own_timer = timers_a.create_timer(tag_ids=[own])["id"]
    schedule_timer = timers_a.create_timer(schedule_id=_schedule(client_a, [sched]))["id"]
    untagged_timer = timers_a.create_timer()["id"]
    for timer_id in (own_timer, schedule_timer, untagged_timer):
        client_a.put(f"/v1/visibility/timer/{timer_id}", json={"level": "public"})
    my_timer = TimerCommands(client_b).create_timer(tag_ids=[tag_b])["id"]

    assert _ids(client_b, scope="shared", tag_ids=[own]) == {own_timer}
    assert _ids(client_b, scope="shared", tag_ids=[own, sched], tag_match="any") == {own_timer, schedule_timer}
    assert _ids(client_b, scope="shared", tag_ids=[tag_b]) == set()
    assert _ids(client_b, scope="all", tag_ids=[own, tag_b], tag_match="any") == {own_timer, my_timer}
    assert _ids(client_b, scope="shared") == {own_timer, schedule_timer, untagged_timer}
