"""
UTC로 바꾸면 표현 범위를 벗어나는 datetime 입력 E2E 테스트

이런 값은 422로 거절된다.
"""
import pytest

TOO_EARLY = "0001-01-01T00:00:00+09:00"
TOO_LATE = "9999-12-31T23:59:59-12:00"


def _create(client) -> str:
    response = client.post(
        "/v1/schedules",
        json={"title": "base", "start_time": "2024-03-10T09:00:00Z", "end_time": "2024-03-10T10:00:00Z",
              "recurrence_rule": "FREQ=DAILY"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.mark.e2e
@pytest.mark.parametrize(
    ("start_time", "end_time"),
    [(TOO_EARLY, "2024-03-10T10:00:00Z"), ("2024-03-10T09:00:00Z", TOO_LATE)],
)
def test_create_schedule_rejects_out_of_range_datetime(e2e_client, start_time, end_time):
    response = e2e_client.post(
        "/v1/schedules", json={"title": "x", "start_time": start_time, "end_time": end_time},
    )

    assert response.status_code == 422, response.text


@pytest.mark.e2e
@pytest.mark.parametrize("body", [{"start_time": TOO_EARLY}, {"end_time": TOO_LATE}, {"recurrence_end": TOO_LATE}])
def test_update_schedule_rejects_out_of_range_datetime(e2e_client, body):
    schedule_id = _create(e2e_client)

    response = e2e_client.patch(f"/v1/schedules/{schedule_id}", json=body)

    assert response.status_code == 422, response.text


@pytest.mark.e2e
@pytest.mark.parametrize(
    "params",
    [
        {"start_date": TOO_EARLY, "end_date": "2024-03-11T00:00:00Z"},
        {"start_date": "2024-03-10T00:00:00Z", "end_date": TOO_LATE},
        {"start_date": TOO_EARLY, "end_date": "2024-03-11T00:00:00Z", "scope": "all"},
    ],
)
def test_schedule_range_rejects_out_of_range_datetime(e2e_client, params):
    response = e2e_client.get("/v1/schedules", params=params)

    assert response.status_code == 422, response.text


@pytest.mark.e2e
@pytest.mark.parametrize("method", ["get", "patch", "delete"])
def test_instance_start_rejects_out_of_range_datetime(e2e_client, method):
    schedule_id = _create(e2e_client)
    kwargs = {"json": {"title": "y"}} if method == "patch" else {}

    response = getattr(e2e_client, method)(
        f"/v1/schedules/{schedule_id}", params={"instance_start": TOO_LATE}, **kwargs
    )

    assert response.status_code == 422, response.text


@pytest.mark.e2e
@pytest.mark.parametrize(
    "params",
    [
        {"start_date": TOO_EARLY},
        {"end_date": TOO_LATE},
        {"start_date": TOO_EARLY, "scope": "all"},
    ],
)
def test_timer_range_rejects_out_of_range_datetime(e2e_client, params):
    response = e2e_client.get("/v1/timers", params=params)

    assert response.status_code == 422, response.text


@pytest.mark.e2e
@pytest.mark.parametrize("params", [{"year": 1}, {"year": 9999}, {"start_year": 1, "end_year": 9999}])
def test_holiday_years_at_the_edges_are_client_errors(e2e_client, params):
    response = e2e_client.get("/v1/holidays", params=params)

    assert 400 <= response.status_code < 500, response.text


@pytest.mark.e2e
@pytest.mark.parametrize(("start", "end"), [("0001-01-01", "0001-01-01"), ("9999-12-31", "9999-12-31")])
def test_graphql_calendar_at_the_edges_does_not_fail(e2e_client, start, end):
    response = e2e_client.post(
        "/v1/graphql",
        json={
            "query": "query($s: Date!, $e: Date!) { calendar(startDate: $s, endDate: $e) { days { date } } }",
            "variables": {"s": start, "e": end},
        },
    )

    assert response.status_code < 500, response.text
    assert "errors" in response.json() or response.json()["data"]["calendar"]["days"] == [{"date": start}]


@pytest.mark.e2e
def test_create_todo_rejects_out_of_range_deadline(e2e_client):
    response = e2e_client.post("/v1/todos", json={"title": "x", "deadline": TOO_EARLY})

    assert response.status_code == 422, response.text
