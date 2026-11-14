"""
일정 구간 경계 E2E 테스트

일정은 [start_time, end_time) 구간이고, 범위 조회는 [start_date, end_date)와 겹치는 일정을 돌려준다.
하루짜리 일정은 다음 날 00:00에 끝난다.
"""
from datetime import datetime, timedelta, timezone

import pytest

OWNER = "user-a"
VIEWER = "user-c"


def _create(client, title: str, start: str, end: str, **extra) -> str:
    response = client.post(
        "/v1/schedules",
        json={"title": title, "start_time": start, "end_time": end, **extra},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _titles(client, start: str, end: str, scope: str = "mine") -> list[str]:
    response = client.get(
        "/v1/schedules",
        params={"start_date": start, "end_date": end, "scope": scope},
    )
    assert response.status_code == 200, response.text
    return [s["title"] for s in response.json()]


@pytest.mark.e2e
def test_schedule_ending_at_range_start_is_excluded(e2e_client):
    _create(e2e_client, "before", "2024-03-10T08:00:00Z", "2024-03-10T10:00:00Z")

    assert _titles(e2e_client, "2024-03-10T10:00:00Z", "2024-03-10T12:00:00Z") == []
    assert _titles(e2e_client, "2024-03-10T09:59:59Z", "2024-03-10T12:00:00Z") == ["before"]


@pytest.mark.e2e
def test_schedule_starting_at_range_end_is_excluded(e2e_client):
    _create(e2e_client, "after", "2024-03-10T12:00:00Z", "2024-03-10T13:00:00Z")

    assert _titles(e2e_client, "2024-03-10T10:00:00Z", "2024-03-10T12:00:00Z") == []
    assert _titles(e2e_client, "2024-03-10T12:00:00Z", "2024-03-10T12:00:01Z") == ["after"]


@pytest.mark.e2e
def test_back_to_back_schedules_do_not_overlap(e2e_client):
    _create(e2e_client, "A", "2024-03-10T09:00:00Z", "2024-03-10T10:00:00Z")
    _create(e2e_client, "B", "2024-03-10T10:00:00Z", "2024-03-10T11:00:00Z")

    # A의 구간으로 조회하면 B는 겹치지 않고, B의 구간으로 조회하면 A는 겹치지 않는다
    assert _titles(e2e_client, "2024-03-10T09:00:00Z", "2024-03-10T10:00:00Z") == ["A"]
    assert _titles(e2e_client, "2024-03-10T10:00:00Z", "2024-03-10T11:00:00Z") == ["B"]


@pytest.mark.e2e
def test_whole_day_schedule_belongs_only_to_its_day(e2e_client):
    _create(e2e_client, "day", "2024-03-10T00:00:00+09:00", "2024-03-11T00:00:00+09:00")

    assert _titles(e2e_client, "2024-03-10T00:00:00+09:00", "2024-03-11T00:00:00+09:00") == ["day"]
    assert _titles(e2e_client, "2024-03-11T00:00:00+09:00", "2024-03-12T00:00:00+09:00") == []
    assert _titles(e2e_client, "2024-03-09T00:00:00+09:00", "2024-03-10T00:00:00+09:00") == []


@pytest.mark.e2e
def test_recurring_whole_day_schedule_has_one_occurrence_per_day(e2e_client):
    parent_id = _create(
        e2e_client, "daily", "2024-03-10T00:00:00+09:00", "2024-03-11T00:00:00+09:00",
        recurrence_rule="FREQ=DAILY",
    )

    for day in range(10, 15):
        response = e2e_client.get(
            "/v1/schedules",
            params={
                "start_date": f"2024-03-{day}T00:00:00+09:00",
                "end_date": f"2024-03-{day + 1}T00:00:00+09:00",
            },
        )
        assert response.status_code == 200, response.text
        items = response.json()
        assert len(items) == 1, items
        assert items[0]["parent_id"] == parent_id
        local_midnight = datetime(2024, 3, day, tzinfo=timezone(timedelta(hours=9)))
        assert datetime.fromisoformat(items[0]["start_time"]) == local_midnight
        assert datetime.fromisoformat(items[0]["end_time"]) == local_midnight + timedelta(days=1)


@pytest.mark.e2e
def test_recurring_occurrence_boundaries_follow_overlap_rule(e2e_client):
    _create(
        e2e_client, "hourly", "2024-03-10T09:00:00Z", "2024-03-10T10:00:00Z",
        recurrence_rule="FREQ=DAILY",
    )

    # 회차 [09:00, 10:00): 10:00부터 시작하는 범위, 09:00에 끝나는 범위와 겹치지 않는다
    assert _titles(e2e_client, "2024-03-11T10:00:00Z", "2024-03-12T09:00:00Z") == []
    assert _titles(e2e_client, "2024-03-11T09:59:59Z", "2024-03-12T09:00:01Z") == ["hourly", "hourly"]


@pytest.mark.e2e
def test_modified_long_occurrence_starting_before_range_uses_exception(e2e_client):
    """범위 시작 전에 시작해 범위와 겹치는 회차도 수정 내용이 반영된다"""
    parent_id = _create(
        e2e_client, "two-day", "2024-03-10T00:00:00Z", "2024-03-12T00:00:00Z",
        recurrence_rule="FREQ=WEEKLY",
    )
    response = e2e_client.patch(
        f"/v1/schedules/{parent_id}",
        params={"instance_start": "2024-03-17T00:00:00Z"},
        json={"title": "renamed"},
    )
    assert response.status_code == 200, response.text

    assert _titles(e2e_client, "2024-03-18T00:00:00Z", "2024-03-19T00:00:00Z") == ["renamed"]


@pytest.mark.e2e
def test_deleting_all_but_last_occurrence_keeps_parent(e2e_client):
    """recurrence_end와 같은 시각에 시작하는 마지막 회차도 회차로 센다"""
    parent_id = _create(
        e2e_client, "three", "2024-03-10T09:00:00Z", "2024-03-10T10:00:00Z",
        recurrence_rule="FREQ=DAILY", recurrence_end="2024-03-12T09:00:00Z",
    )
    for day in (10, 11):
        response = e2e_client.delete(
            f"/v1/schedules/{parent_id}",
            params={"instance_start": f"2024-03-{day}T09:00:00Z"},
        )
        assert response.status_code == 200, response.text

    assert e2e_client.get(f"/v1/schedules/{parent_id}").status_code == 200
    assert _titles(e2e_client, "2024-03-12T00:00:00Z", "2024-03-13T00:00:00Z") == ["three"]


@pytest.mark.e2e
def test_shared_schedules_follow_overlap_rule(multi_user_e2e):
    owner = multi_user_e2e.as_user(OWNER)
    viewer = multi_user_e2e.as_user(VIEWER)
    for title, start, end, extra in (
        ("single", "2024-03-10T08:00:00Z", "2024-03-10T10:00:00Z", {}),
        ("daily", "2024-03-10T12:00:00Z", "2024-03-10T13:00:00Z", {"recurrence_rule": "FREQ=DAILY"}),
    ):
        schedule_id = _create(owner, title, start, end, **extra)
        response = owner.put(f"/v1/visibility/schedule/{schedule_id}", json={"level": "public"})
        assert response.status_code == 200, response.text

    assert _titles(viewer, "2024-03-10T10:00:00Z", "2024-03-10T12:00:00Z", scope="shared") == []
    assert _titles(viewer, "2024-03-10T13:00:00Z", "2024-03-11T12:00:00Z", scope="shared") == []
    assert _titles(viewer, "2024-03-10T09:00:00Z", "2024-03-10T12:00:01Z", scope="shared") == [
        "single", "daily",
    ]


CALENDAR_QUERY = """
query GetCalendar($startDate: Date!, $endDate: Date!) {
    calendar(startDate: $startDate, endDate: $endDate) {
        days { date events { title } }
    }
}
"""


def _calendar(client, start: str, end: str) -> dict[str, list[str]]:
    response = client.post(
        "/v1/graphql",
        json={"query": CALENDAR_QUERY, "variables": {"startDate": start, "endDate": end}},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "errors" not in body, body
    return {
        day["date"]: [event["title"] for event in day["events"]]
        for day in body["data"]["calendar"]["days"]
    }


@pytest.mark.e2e
def test_graphql_calendar_places_whole_day_schedule_on_its_day_only(e2e_client):
    _create(e2e_client, "day", "2024-03-10T00:00:00Z", "2024-03-11T00:00:00Z")
    _create(e2e_client, "evening", "2024-03-11T22:00:00Z", "2024-03-12T00:00:00Z")

    assert _calendar(e2e_client, "2024-03-10", "2024-03-12") == {
        "2024-03-10": ["day"],
        "2024-03-11": ["evening"],
        "2024-03-12": [],
    }
    assert _calendar(e2e_client, "2024-03-12", "2024-03-12") == {"2024-03-12": []}


@pytest.mark.e2e
def test_graphql_calendar_includes_schedule_on_end_date(e2e_client):
    _create(e2e_client, "late", "2024-03-12T23:30:00Z", "2024-03-13T00:30:00Z")

    assert _calendar(e2e_client, "2024-03-12", "2024-03-12") == {"2024-03-12": ["late"]}
