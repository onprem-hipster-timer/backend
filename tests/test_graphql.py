"""
GraphQL API 테스트

Strawberry GraphQL 엔드포인트를 테스트합니다.
"""
import pytest
from datetime import date, datetime, UTC


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
                "title": f"일정 {i+1}",
                "start_time": f"2024-02-{10+i:02d}T10:00:00Z",
                "end_time": f"2024-02-{10+i:02d}T12:00:00Z",
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

