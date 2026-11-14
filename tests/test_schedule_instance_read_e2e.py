"""
반복 일정 인스턴스 단건 조회 E2E 테스트

GET /v1/schedules/{parent_id}?instance_start=... 는 목록이 주는 인스턴스와 같은 모양을 반환한다.
"""
import pytest

WEEKLY_MONDAY = {
    "title": "주간 회의",
    "description": "매주 월요일",
    "start_time": "2024-01-01T10:00:00Z",  # 월요일
    "end_time": "2024-01-01T12:00:00Z",
    "recurrence_rule": "FREQ=WEEKLY;BYDAY=MO",
    "recurrence_end": "2024-01-29T23:59:59Z",  # 1, 8, 15, 22, 29일
}


def _create_weekly(client) -> str:
    response = client.post("/v1/schedules", json=WEEKLY_MONDAY)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _list_instance(client, parent_id: str, start_date: str, end_date: str, **params) -> dict:
    response = client.get(
        "/v1/schedules",
        params={"start_date": start_date, "end_date": end_date, **params},
    )
    assert response.status_code == 200, response.text
    instances = [s for s in response.json() if s["parent_id"] == parent_id]
    assert len(instances) == 1, instances
    return instances[0]


def _get_instance(client, parent_id: str, instance_start: str, **params):
    return client.get(
        f"/v1/schedules/{parent_id}",
        params={"instance_start": instance_start, **params},
    )


def _without_id(item: dict) -> dict:
    return {k: v for k, v in item.items() if k != "id"}


@pytest.mark.e2e
def test_instance_read_matches_list_instance(e2e_client):
    parent_id = _create_weekly(e2e_client)

    listed = _list_instance(e2e_client, parent_id, "2024-01-08T00:00:00Z", "2024-01-08T23:59:59Z")
    response = _get_instance(e2e_client, parent_id, "2024-01-08T10:00:00Z")

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["parent_id"] == parent_id
    assert data["start_time"] == "2024-01-08T10:00:00+0000"
    assert data["end_time"] == "2024-01-08T12:00:00+0000"
    assert data["recurrence_rule"] is None
    assert data["is_shared"] is False
    assert _without_id(data) == _without_id(listed)


@pytest.mark.e2e
def test_instance_read_returns_modified_exception_fields(e2e_client):
    parent_id = _create_weekly(e2e_client)
    patch = e2e_client.patch(
        f"/v1/schedules/{parent_id}",
        params={"instance_start": "2024-01-15T10:00:00Z"},
        json={
            "title": "변경된 회의",
            "start_time": "2024-01-15T13:00:00Z",
            "end_time": "2024-01-15T14:00:00Z",
        },
    )
    assert patch.status_code == 200, patch.text

    response = _get_instance(e2e_client, parent_id, "2024-01-15T10:00:00Z")

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["title"] == "변경된 회의"
    assert data["description"] == "매주 월요일"
    assert data["start_time"] == "2024-01-15T13:00:00+0000"
    assert data["end_time"] == "2024-01-15T14:00:00+0000"
    listed = _list_instance(e2e_client, parent_id, "2024-01-15T00:00:00Z", "2024-01-15T23:59:59Z")
    assert _without_id(data) == _without_id(listed)


@pytest.mark.e2e
def test_instance_read_deleted_occurrence_is_404(e2e_client):
    parent_id = _create_weekly(e2e_client)
    delete = e2e_client.delete(
        f"/v1/schedules/{parent_id}", params={"instance_start": "2024-01-22T10:00:00Z"}
    )
    assert delete.status_code == 200, delete.text

    assert _get_instance(e2e_client, parent_id, "2024-01-22T10:00:00Z").status_code == 404
    # 다른 회차는 그대로 조회된다
    assert _get_instance(e2e_client, parent_id, "2024-01-15T10:00:00Z").status_code == 200


@pytest.mark.e2e
def test_instance_read_deleted_then_restored_occurrence(e2e_client):
    parent_id = _create_weekly(e2e_client)
    e2e_client.delete(f"/v1/schedules/{parent_id}", params={"instance_start": "2024-01-22T10:00:00Z"})
    restore = e2e_client.patch(
        f"/v1/schedules/{parent_id}",
        params={"instance_start": "2024-01-22T10:00:00Z"},
        json={"title": "복구된 회의"},
    )
    assert restore.status_code == 200, restore.text

    response = _get_instance(e2e_client, parent_id, "2024-01-22T10:00:00Z")

    assert response.status_code == 200, response.text
    assert response.json()["title"] == "복구된 회의"


@pytest.mark.e2e
@pytest.mark.parametrize(
    "instance_start",
    [
        "2024-01-09T10:00:00Z",  # 규칙에 없는 요일
        "2024-01-08T10:30:00Z",  # 규칙의 날짜지만 다른 시각
        "2024-01-08T10:01:01Z",  # 허용 오차(60초) 바로 밖
        "2023-12-25T10:00:00Z",  # 첫 회차 이전
        "2024-02-05T10:00:00Z",  # recurrence_end 이후
    ],
)
def test_instance_read_without_occurrence_is_404(e2e_client, instance_start):
    parent_id = _create_weekly(e2e_client)

    assert _get_instance(e2e_client, parent_id, instance_start).status_code == 404


@pytest.mark.e2e
def test_instance_read_first_and_last_occurrence(e2e_client):
    parent_id = _create_weekly(e2e_client)

    first = _get_instance(e2e_client, parent_id, "2024-01-01T10:00:00Z")
    last = _get_instance(e2e_client, parent_id, "2024-01-29T10:00:00Z")

    assert first.status_code == 200, first.text
    assert first.json()["start_time"] == "2024-01-01T10:00:00+0000"
    assert last.status_code == 200, last.text
    assert last.json()["start_time"] == "2024-01-29T10:00:00+0000"


@pytest.mark.e2e
def test_instance_read_within_tolerance_returns_rule_start(e2e_client):
    parent_id = _create_weekly(e2e_client)

    response = _get_instance(e2e_client, parent_id, "2024-01-08T10:00:30Z")

    assert response.status_code == 200, response.text
    assert response.json()["start_time"] == "2024-01-08T10:00:00+0000"


@pytest.mark.e2e
def test_instance_read_with_offset_and_timezone_param(e2e_client):
    parent_id = _create_weekly(e2e_client)

    response = _get_instance(
        e2e_client, parent_id, "2024-01-08T19:00:00+09:00", timezone="Asia/Seoul"
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["start_time"] == "2024-01-08T19:00:00+0900"
    assert data["end_time"] == "2024-01-08T21:00:00+0900"
    listed = _list_instance(
        e2e_client, parent_id, "2024-01-08T00:00:00Z", "2024-01-08T23:59:59Z", timezone="Asia/Seoul"
    )
    assert _without_id(data) == _without_id(listed)


@pytest.mark.e2e
def test_read_without_instance_start_returns_parent(e2e_client):
    parent_id = _create_weekly(e2e_client)

    response = e2e_client.get(f"/v1/schedules/{parent_id}")

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["id"] == parent_id
    assert data["parent_id"] is None
    assert data["recurrence_rule"] == "FREQ=WEEKLY;BYDAY=MO"
    assert data["start_time"] == "2024-01-01T10:00:00+0000"


@pytest.mark.e2e
def test_instance_read_on_non_recurring_schedule_matches_patch_and_delete(e2e_client):
    schedule_id = e2e_client.post(
        "/v1/schedules",
        json={"title": "단일 일정", "start_time": "2024-01-08T10:00:00Z", "end_time": "2024-01-08T12:00:00Z"},
    ).json()["id"]
    params = {"instance_start": "2024-01-08T10:00:00Z"}

    read = e2e_client.get(f"/v1/schedules/{schedule_id}", params=params)
    patch = e2e_client.patch(f"/v1/schedules/{schedule_id}", params=params, json={"title": "x"})
    delete = e2e_client.delete(f"/v1/schedules/{schedule_id}", params=params)

    assert read.status_code == 400, read.text
    assert read.json()["error_type"] == "RecurringScheduleError"
    assert patch.status_code == read.status_code
    assert delete.status_code == read.status_code


@pytest.mark.e2e
def test_instance_read_unknown_schedule_is_404(e2e_client):
    response = _get_instance(
        e2e_client, "00000000-0000-0000-0000-000000000000", "2024-01-08T10:00:00Z"
    )

    assert response.status_code == 404


@pytest.mark.e2e
def test_instance_read_of_private_schedule_same_status_as_parent_read(multi_user_e2e):
    client_a = multi_user_e2e.as_user("user-a")
    client_b = multi_user_e2e.as_user("user-b")
    parent_id = _create_weekly(client_a)

    parent_read = client_b.get(f"/v1/schedules/{parent_id}")
    instance_read = _get_instance(client_b, parent_id, "2024-01-08T10:00:00Z")
    off_rule_read = _get_instance(client_b, parent_id, "2024-01-09T10:00:00Z")

    assert parent_read.status_code == 403
    assert instance_read.status_code == parent_read.status_code
    assert off_rule_read.status_code == parent_read.status_code
    assert "주간 회의" not in instance_read.text
