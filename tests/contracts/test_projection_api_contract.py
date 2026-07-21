"""Public API contracts for Todo/Schedule projection fields.

These tests deliberately cover the generated OpenAPI document as well as the
runtime REST response.  A DTO default is observable by generated clients even
when the service later derives a different value, so service-only tests are not
enough for these contracts.
"""

import pytest

from app.main import app


def _component_schema(name: str) -> dict:
    return app.openapi()["components"]["schemas"][name]


def test_todo_create_openapi_has_no_static_status_default():
    """Omitted status is server-derived from deadline, not UNSCHEDULED by schema."""
    todo_create = _component_schema("TodoCreate")
    status = todo_create["properties"]["status"]

    assert "status" not in todo_create.get("required", [])
    assert "default" not in status


@pytest.mark.parametrize("request_schema", ["ScheduleCreate", "ScheduleUpdate"])
def test_schedule_write_openapi_does_not_advertise_source_todo_id(request_schema):
    """Projection linkage is managed by dedicated flows, never direct writes."""
    properties = _component_schema(request_schema)["properties"]

    assert "source_todo_id" not in properties


def test_schedule_read_openapi_keeps_source_todo_id():
    """Clients still need the linkage identifier in Schedule responses."""
    properties = _component_schema("ScheduleRead")["properties"]

    assert "source_todo_id" in properties


@pytest.mark.e2e
def test_omitted_todo_status_is_derived_from_deadline_in_rest_response(e2e_client):
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "Todo status contract", "color": "#3366FF"},
    )
    assert group_response.status_code == 201
    group_id = group_response.json()["id"]

    without_deadline = e2e_client.post(
        "/v1/todos",
        json={
            "title": "No deadline",
            "tag_group_id": group_id,
        },
    )
    with_deadline = e2e_client.post(
        "/v1/todos",
        json={
            "title": "Has deadline",
            "tag_group_id": group_id,
            "deadline": "2030-01-01T12:00:00Z",
        },
    )

    assert without_deadline.status_code == 201
    assert with_deadline.status_code == 201

    without_deadline_body = without_deadline.json()
    with_deadline_body = with_deadline.json()
    assert without_deadline_body["status"] == "UNSCHEDULED"
    assert without_deadline_body["deadline"] is None
    assert without_deadline_body["schedules"] == []
    assert with_deadline_body["status"] == "SCHEDULED"
    assert with_deadline_body["deadline"] is not None
    assert len(with_deadline_body["schedules"]) == 1

