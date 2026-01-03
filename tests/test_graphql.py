"""
GraphQL API 테스트

Strawberry GraphQL 엔드포인트를 테스트합니다.
"""
import pytest


@pytest.mark.e2e
def test_graphql_calendar_query(e2e_client):
    """GraphQL calendar 쿼리 테스트"""
    # 1. 일정 생성 (REST API 사용)
    create_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "GraphQL 테스트 일정",
            "description": "GraphQL 테스트 설명",
            "start_time": "2024-01-15T10:00:00Z",
            "end_time": "2024-01-15T12:00:00Z",
        },
    )
    assert create_response.status_code == 201

    # 2. GraphQL 쿼리 실행
    query = """
    query GetCalendar($startDate: Date!, $endDate: Date!) {
        calendar(startDate: $startDate, endDate: $endDate) {
            days {
                date
                events {
                    id
                    title
                    description
                    startAt
                    endAt
                    createdAt
                    isRecurring
                    parentId
                    instanceStart
                }
            }
        }
    }
    """

    variables = {
        "startDate": "2024-01-01",
        "endDate": "2024-01-31",
    }

    response = e2e_client.post(
        "/v1/graphql",
        json={
            "query": query,
            "variables": variables,
        },
    )

    assert response.status_code == 200
    data = response.json()

    # GraphQL 응답 구조 확인
    assert "data" in data
    assert "calendar" in data["data"]
    assert "days" in data["data"]["calendar"]

    # 일정이 포함된 날짜 찾기
    days = data["data"]["calendar"]["days"]
    assert isinstance(days, list)

    # 2024-01-15 날짜 찾기
    target_day = None
    for day in days:
        if day["date"] == "2024-01-15":
            target_day = day
            break

    assert target_day is not None, "일정이 포함된 날짜를 찾을 수 없습니다"
    assert len(target_day["events"]) > 0, "일정이 포함되어야 합니다"

    # 일정 데이터 확인
    event = target_day["events"][0]
    assert event["title"] == "GraphQL 테스트 일정"
    assert event["description"] == "GraphQL 테스트 설명"
    assert "id" in event
    assert "startAt" in event
    assert "endAt" in event
    assert "createdAt" in event
    assert event["isRecurring"] is False
    assert event["parentId"] is None
    assert event["instanceStart"] is None


@pytest.mark.e2e
def test_graphql_calendar_query_multiple_events(e2e_client):
    """여러 일정이 있는 GraphQL calendar 쿼리 테스트"""
    # 1. 여러 일정 생성
    for i in range(3):
        e2e_client.post(
            "/v1/schedules",
            json={
                "title": f"일정 {i + 1}",
                "start_time": f"2024-02-{10 + i:02d}T10:00:00Z",
                "end_time": f"2024-02-{10 + i:02d}T12:00:00Z",
            },
        )

    # 2. GraphQL 쿼리 실행
    query = """
    query GetCalendar($startDate: Date!, $endDate: Date!) {
        calendar(startDate: $startDate, endDate: $endDate) {
            days {
                date
                events {
                    title
                    isRecurring
                    parentId
                    instanceStart
                }
            }
        }
    }
    """

    variables = {
        "startDate": "2024-02-01",
        "endDate": "2024-02-28",
    }

    response = e2e_client.post(
        "/v1/graphql",
        json={
            "query": query,
            "variables": variables,
        },
    )

    assert response.status_code == 200
    data = response.json()

    # 모든 날짜에 일정이 있는지 확인
    days = data["data"]["calendar"]["days"]
    event_count = sum(len(day["events"]) for day in days)
    assert event_count >= 3, "최소 3개의 일정이 있어야 합니다"


@pytest.mark.e2e
def test_graphql_calendar_query_empty_range(e2e_client):
    """일정이 없는 날짜 범위에 대한 GraphQL 쿼리 테스트"""
    query = """
    query GetCalendar($startDate: Date!, $endDate: Date!) {
        calendar(startDate: $startDate, endDate: $endDate) {
            days {
                date
                events {
                    title
                    isRecurring
                    parentId
                    instanceStart
                }
            }
        }
    }
    """

    variables = {
        "startDate": "2024-03-01",
        "endDate": "2024-03-07",
    }

    response = e2e_client.post(
        "/v1/graphql",
        json={
            "query": query,
            "variables": variables,
        },
    )

    assert response.status_code == 200
    data = response.json()

    # 일정이 없는 날짜 범위도 정상적으로 반환되어야 함
    assert "data" in data
    assert "calendar" in data["data"]
    days = data["data"]["calendar"]["days"]

    # 7일이 모두 포함되어야 함
    assert len(days) == 7

    # 모든 날짜의 events가 빈 배열이어야 함
    for day in days:
        assert day["events"] == []


@pytest.mark.e2e
def test_graphql_calendar_query_cross_day_event(e2e_client):
    """하루 이상 걸치는 일정에 대한 GraphQL 쿼리 테스트"""
    # 1. 여러 날짜에 걸치는 일정 생성
    e2e_client.post(
        "/v1/schedules",
        json={
            "title": "2일간 일정",
            "start_time": "2024-04-15T10:00:00Z",
            "end_time": "2024-04-16T18:00:00Z",
        },
    )

    # 2. GraphQL 쿼리 실행
    query = """
    query GetCalendar($startDate: Date!, $endDate: Date!) {
        calendar(startDate: $startDate, endDate: $endDate) {
            days {
                date
                events {
                    title
                    isRecurring
                    parentId
                    instanceStart
                }
            }
        }
    }
    """

    variables = {
        "startDate": "2024-04-14",
        "endDate": "2024-04-17",
    }

    response = e2e_client.post(
        "/v1/graphql",
        json={
            "query": query,
            "variables": variables,
        },
    )

    assert response.status_code == 200
    data = response.json()

    days = data["data"]["calendar"]["days"]

    # 4월 15일과 16일 모두에 일정이 포함되어야 함
    dates_with_events = [day["date"] for day in days if len(day["events"]) > 0]
    assert "2024-04-15" in dates_with_events
    assert "2024-04-16" in dates_with_events


@pytest.mark.e2e
def test_graphql_invalid_query(e2e_client):
    """잘못된 GraphQL 쿼리 테스트"""
    query = """
    query InvalidQuery {
        nonExistentField {
            id
        }
    }
    """

    response = e2e_client.post(
        "/v1/graphql",
        json={
            "query": query,
        },
    )

    assert response.status_code == 200  # GraphQL은 항상 200을 반환
    data = response.json()

    # 에러가 포함되어야 함
    assert "errors" in data
    assert len(data["errors"]) > 0


@pytest.mark.e2e
def test_graphql_missing_variables(e2e_client):
    """필수 변수가 없는 GraphQL 쿼리 테스트"""
    query = """
    query GetCalendar($startDate: Date!, $endDate: Date!) {
        calendar(startDate: $startDate, endDate: $endDate) {
            days {
                date
            }
        }
    }
    """

    response = e2e_client.post(
        "/v1/graphql",
        json={
            "query": query,
            # variables 누락
        },
    )

    assert response.status_code == 200  # GraphQL은 항상 200을 반환
    data = response.json()

    # 에러가 포함되어야 함
    assert "errors" in data
    assert len(data["errors"]) > 0


@pytest.mark.e2e
def test_graphql_introspection_query(e2e_client):
    """GraphQL introspection 쿼리 테스트"""
    query = """
    query IntrospectionQuery {
        __schema {
            queryType {
                name
            }
            types {
                name
            }
        }
    }
    """

    response = e2e_client.post(
        "/v1/graphql",
        json={
            "query": query,
        },
    )

    assert response.status_code == 200
    data = response.json()

    # Introspection이 정상적으로 작동해야 함
    assert "data" in data
    assert "__schema" in data["data"]
    assert "queryType" in data["data"]["__schema"]
    assert "types" in data["data"]["__schema"]


@pytest.mark.e2e
def test_graphql_calendar_query_with_recurring_schedule(e2e_client):
    """반복 일정이 있는 GraphQL calendar 쿼리 테스트"""
    # 1. 반복 일정 생성
    create_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "매주 반복 일정",
            "start_time": "2024-05-01T10:00:00Z",
            "end_time": "2024-05-01T12:00:00Z",
            "recurrence_rule": "FREQ=WEEKLY;COUNT=4",
        },
    )
    assert create_response.status_code == 201

    # 2. GraphQL 쿼리 실행
    query = """
    query GetCalendar($startDate: Date!, $endDate: Date!) {
        calendar(startDate: $startDate, endDate: $endDate) {
            days {
                date
                events {
                    title
                    isRecurring
                    parentId
                    instanceStart
                }
            }
        }
    }
    """

    variables = {
        "startDate": "2024-05-01",
        "endDate": "2024-05-31",
    }

    response = e2e_client.post(
        "/v1/graphql",
        json={
            "query": query,
            "variables": variables,
        },
    )

    assert response.status_code == 200
    data = response.json()

    days = data["data"]["calendar"]["days"]

    # 반복 일정이 여러 날짜에 나타나야 함
    recurring_events = []
    for day in days:
        for event in day["events"]:
            if event["title"] == "매주 반복 일정":
                recurring_events.append(event)

    assert len(recurring_events) >= 4, "최소 4개의 반복 일정 인스턴스가 있어야 합니다"

    # 첫 번째 일정은 isRecurring이 True여야 함
    if recurring_events:
        assert recurring_events[0]["isRecurring"] is True
        # 반복 일정의 경우 parentId와 instanceStart 확인
        # 첫 번째는 원본이므로 parentId가 None일 수 있음
        # 인스턴스들은 parentId가 있고 instanceStart가 설정되어야 함
        for event in recurring_events:
            assert "parentId" in event
            assert "instanceStart" in event


@pytest.mark.e2e
def test_graphql_calendar_query_with_tag_filter(e2e_client):
    """GraphQL calendar 쿼리 태그 필터링 테스트"""
    # 1. 태그 그룹 및 태그 생성
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "업무", "color": "#FF5733"}
    )
    group_id = group_response.json()["id"]
    
    tag1_response = e2e_client.post(
        "/v1/tags",
        json={"name": "중요", "color": "#FF0000", "group_id": group_id}
    )
    tag1_id = tag1_response.json()["id"]
    
    tag2_response = e2e_client.post(
        "/v1/tags",
        json={"name": "긴급", "color": "#00FF00", "group_id": group_id}
    )
    tag2_id = tag2_response.json()["id"]
    
    # 2. 일정 생성 및 태그 추가
    schedule1_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "태그 있는 일정 1",
            "start_time": "2024-01-15T10:00:00Z",
            "end_time": "2024-01-15T12:00:00Z",
        }
    )
    schedule1_id = schedule1_response.json()["id"]
    e2e_client.put(
        f"/v1/tags/schedules/{schedule1_id}/tags",
        json=[tag1_id, tag2_id]  # 두 태그 모두
    )
    
    schedule2_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "태그 있는 일정 2",
            "start_time": "2024-01-16T10:00:00Z",
            "end_time": "2024-01-16T12:00:00Z",
        }
    )
    schedule2_id = schedule2_response.json()["id"]
    e2e_client.put(
        f"/v1/tags/schedules/{schedule2_id}/tags",
        json=[tag1_id]  # tag1만
    )
    
    schedule3_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "태그 없는 일정",
            "start_time": "2024-01-17T10:00:00Z",
            "end_time": "2024-01-17T12:00:00Z",
        }
    )
    
    # 3. 태그 필터링 쿼리 (tag1 AND tag2)
    query = """
    query GetCalendar($startDate: Date!, $endDate: Date!, $tagFilter: TagFilterInput) {
        calendar(startDate: $startDate, endDate: $endDate, tagFilter: $tagFilter) {
            days {
                date
                events {
                    id
                    title
                    tags {
                        id
                        name
                    }
                }
            }
        }
    }
    """
    
    variables = {
        "startDate": "2024-01-01",
        "endDate": "2024-01-31",
        "tagFilter": {
            "tagIds": [tag1_id, tag2_id]  # AND 방식
        }
    }
    
    response = e2e_client.post(
        "/v1/graphql",
        json={"query": query, "variables": variables}
    )
    assert response.status_code == 200
    
    data = response.json()["data"]["calendar"]
    events = []
    for day in data["days"]:
        events.extend(day["events"])
    
    # tag1 AND tag2를 가진 일정만 반환되어야 함 (schedule1만)
    assert len(events) == 1
    assert events[0]["id"] == schedule1_id
    assert len(events[0]["tags"]) == 2


@pytest.mark.e2e
def test_graphql_calendar_query_with_group_filter(e2e_client):
    """GraphQL calendar 쿼리 그룹 필터링 테스트"""
    # 1. 태그 그룹 및 태그 생성
    group1_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "업무", "color": "#FF5733"}
    )
    group1_id = group1_response.json()["id"]
    
    group2_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "개인", "color": "#00FF00"}
    )
    group2_id = group2_response.json()["id"]
    
    tag1_response = e2e_client.post(
        "/v1/tags",
        json={"name": "중요", "color": "#FF0000", "group_id": group1_id}
    )
    tag1_id = tag1_response.json()["id"]
    
    tag2_response = e2e_client.post(
        "/v1/tags",
        json={"name": "긴급", "color": "#0000FF", "group_id": group2_id}
    )
    tag2_id = tag2_response.json()["id"]
    
    # 2. 일정 생성 및 태그 추가
    schedule1_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "업무 그룹 태그 일정",
            "start_time": "2024-01-15T10:00:00Z",
            "end_time": "2024-01-15T12:00:00Z",
        }
    )
    schedule1_id = schedule1_response.json()["id"]
    e2e_client.put(
        f"/v1/tags/schedules/{schedule1_id}/tags",
        json=[tag1_id]
    )
    
    schedule2_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "개인 그룹 태그 일정",
            "start_time": "2024-01-16T10:00:00Z",
            "end_time": "2024-01-16T12:00:00Z",
        }
    )
    schedule2_id = schedule2_response.json()["id"]
    e2e_client.put(
        f"/v1/tags/schedules/{schedule2_id}/tags",
        json=[tag2_id]
    )
    
    # 3. 그룹 필터링 쿼리
    query = """
    query GetCalendar($startDate: Date!, $endDate: Date!, $tagFilter: TagFilterInput) {
        calendar(startDate: $startDate, endDate: $endDate, tagFilter: $tagFilter) {
            days {
                date
                events {
                    id
                    title
                    tags {
                        id
                        name
                    }
                }
            }
        }
    }
    """
    
    variables = {
        "startDate": "2024-01-01",
        "endDate": "2024-01-31",
        "tagFilter": {
            "groupIds": [group1_id]  # 업무 그룹만
        }
    }
    
    response = e2e_client.post(
        "/v1/graphql",
        json={"query": query, "variables": variables}
    )
    assert response.status_code == 200
    
    data = response.json()["data"]["calendar"]
    events = []
    for day in data["days"]:
        events.extend(day["events"])
    
    # 업무 그룹의 태그를 가진 일정만 반환되어야 함 (schedule1만)
    assert len(events) == 1
    assert events[0]["id"] == schedule1_id


@pytest.mark.e2e
def test_graphql_calendar_query_with_tag_and_group_filter(e2e_client):
    """GraphQL calendar 쿼리 태그와 그룹 필터링 조합 테스트"""
    # 1. 태그 그룹 및 태그 생성
    group1_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "업무", "color": "#FF5733"}
    )
    group1_id = group1_response.json()["id"]
    
    group2_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "개인", "color": "#00FF00"}
    )
    group2_id = group2_response.json()["id"]
    
    tag1_response = e2e_client.post(
        "/v1/tags",
        json={"name": "중요", "color": "#FF0000", "group_id": group1_id}
    )
    tag1_id = tag1_response.json()["id"]
    
    tag2_response = e2e_client.post(
        "/v1/tags",
        json={"name": "긴급", "color": "#0000FF", "group_id": group1_id}
    )
    tag2_id = tag2_response.json()["id"]
    
    tag3_response = e2e_client.post(
        "/v1/tags",
        json={"name": "개인용", "color": "#FFFF00", "group_id": group2_id}
    )
    tag3_id = tag3_response.json()["id"]
    
    # 2. 일정 생성 및 태그 추가
    schedule1_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "업무 그룹 태그 2개 일정",
            "start_time": "2024-01-15T10:00:00Z",
            "end_time": "2024-01-15T12:00:00Z",
        }
    )
    schedule1_id = schedule1_response.json()["id"]
    e2e_client.put(
        f"/v1/tags/schedules/{schedule1_id}/tags",
        json=[tag1_id, tag2_id]  # 업무 그룹 태그 2개
    )
    
    schedule2_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "개인 그룹 태그 일정",
            "start_time": "2024-01-16T10:00:00Z",
            "end_time": "2024-01-16T12:00:00Z",
        }
    )
    schedule2_id = schedule2_response.json()["id"]
    e2e_client.put(
        f"/v1/tags/schedules/{schedule2_id}/tags",
        json=[tag3_id]  # 개인 그룹 태그
    )
    
    # 3. 태그 ID와 그룹 ID 필터링 조합 (tag1 AND group1)
    query = """
    query GetCalendar($startDate: Date!, $endDate: Date!, $tagFilter: TagFilterInput) {
        calendar(startDate: $startDate, endDate: $endDate, tagFilter: $tagFilter) {
            days {
                date
                events {
                    id
                    title
                    tags {
                        id
                        name
                    }
                }
            }
        }
    }
    """
    
    variables = {
        "startDate": "2024-01-01",
        "endDate": "2024-01-31",
        "tagFilter": {
            "tagIds": [tag1_id],  # tag1 포함
            "groupIds": [group1_id]  # 업무 그룹 포함
        }
    }
    
    response = e2e_client.post(
        "/v1/graphql",
        json={"query": query, "variables": variables}
    )
    assert response.status_code == 200
    
    data = response.json()["data"]["calendar"]
    events = []
    for day in data["days"]:
        events.extend(day["events"])
    
    # tag1을 가진 일정이어야 하고, 업무 그룹의 태그를 가진 일정도 포함
    # schedule1 (tag1, tag2 모두 업무 그룹)만 반환되어야 함
    assert len(events) == 1
    assert events[0]["id"] == schedule1_id


@pytest.mark.e2e
def test_graphql_calendar_query_without_tag_filter(e2e_client):
    """GraphQL calendar 쿼리 태그 필터링 없이 태그 정보 포함 테스트"""
    # 1. 태그 그룹 및 태그 생성
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "업무", "color": "#FF5733"}
    )
    group_id = group_response.json()["id"]
    
    tag_response = e2e_client.post(
        "/v1/tags",
        json={"name": "중요", "color": "#FF0000", "group_id": group_id}
    )
    tag_id = tag_response.json()["id"]
    
    # 2. 일정 생성 및 태그 추가
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "태그 있는 일정",
            "start_time": "2024-01-15T10:00:00Z",
            "end_time": "2024-01-15T12:00:00Z",
        }
    )
    schedule_id = schedule_response.json()["id"]
    e2e_client.put(
        f"/v1/tags/schedules/{schedule_id}/tags",
        json=[tag_id]
    )
    
    # 3. 태그 필터링 없이 쿼리 (태그 정보 포함)
    query = """
    query GetCalendar($startDate: Date!, $endDate: Date!) {
        calendar(startDate: $startDate, endDate: $endDate) {
            days {
                date
                events {
                    id
                    title
                    tags {
                        id
                        name
                        color
                    }
                }
            }
        }
    }
    """
    
    variables = {
        "startDate": "2024-01-01",
        "endDate": "2024-01-31",
    }
    
    response = e2e_client.post(
        "/v1/graphql",
        json={"query": query, "variables": variables}
    )
    assert response.status_code == 200
    
    data = response.json()["data"]["calendar"]
    events = []
    for day in data["days"]:
        events.extend(day["events"])
    
    # 태그 필터링 없이 모든 일정 반환 (태그 정보 포함)
    tagged_events = [e for e in events if e.get("tags")]
    assert len(tagged_events) >= 1
    
    # 태그가 있는 일정 확인
    tagged_event = next((e for e in events if e["id"] == schedule_id), None)
    assert tagged_event is not None
    assert len(tagged_event["tags"]) == 1
    assert tagged_event["tags"][0]["id"] == tag_id
    assert tagged_event["tags"][0]["name"] == "중요"


@pytest.mark.e2e
def test_graphql_calendar_query_tag_filter_empty_result(e2e_client):
    """GraphQL calendar 쿼리 태그 필터링 빈 결과 테스트"""
    # 1. 태그 그룹 및 태그 생성
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "업무", "color": "#FF5733"}
    )
    group_id = group_response.json()["id"]
    
    tag_response = e2e_client.post(
        "/v1/tags",
        json={"name": "중요", "color": "#FF0000", "group_id": group_id}
    )
    tag_id = tag_response.json()["id"]
    
    # 2. 태그 없는 일정 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "태그 없는 일정",
            "start_time": "2024-01-15T10:00:00Z",
            "end_time": "2024-01-15T12:00:00Z",
        }
    )
    
    # 3. 존재하지 않는 태그로 필터링
    query = """
    query GetCalendar($startDate: Date!, $endDate: Date!, $tagFilter: TagFilterInput) {
        calendar(startDate: $startDate, endDate: $endDate, tagFilter: $tagFilter) {
            days {
                date
                events {
                    id
                    title
                }
            }
        }
    }
    """
    
    from uuid import uuid4
    fake_tag_id = str(uuid4())
    
    variables = {
        "startDate": "2024-01-01",
        "endDate": "2024-01-31",
        "tagFilter": {
            "tagIds": [fake_tag_id]  # 존재하지 않는 태그
        }
    }
    
    response = e2e_client.post(
        "/v1/graphql",
        json={"query": query, "variables": variables}
    )
    assert response.status_code == 200
    
    data = response.json()["data"]["calendar"]
    events = []
    for day in data["days"]:
        events.extend(day["events"])
    
    # 존재하지 않는 태그로 필터링하면 빈 결과
    assert len(events) == 0