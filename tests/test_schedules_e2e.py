import pytest


@pytest.mark.e2e
def test_create_schedule_e2e(e2e_client):
    """HTTP를 통한 일정 생성 E2E 테스트"""
    response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "E2E 테스트 일정",
            "description": "E2E 테스트 설명",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "E2E 테스트 일정"
    assert data["description"] == "E2E 테스트 설명"
    assert "id" in data
    assert "created_at" in data


@pytest.mark.e2e
def test_get_schedule_e2e(e2e_client):
    """HTTP를 통한 일정 조회 E2E 테스트"""
    # 1. 일정 생성
    create_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "조회 테스트 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    assert create_response.status_code == 201
    schedule_id = create_response.json()["id"]

    # 2. 일정 조회
    get_response = e2e_client.get(f"/v1/schedules/{schedule_id}")
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["id"] == schedule_id
    assert data["title"] == "조회 테스트 일정"


@pytest.mark.e2e
def test_get_schedule_not_found_e2e(e2e_client):
    """존재하지 않는 일정 조회 E2E 테스트"""
    from uuid import uuid4

    non_existent_id = str(uuid4())
    response = e2e_client.get(f"/v1/schedules/{non_existent_id}")

    assert response.status_code == 404
    # Exception Handler는 "message" 필드를 반환 (ErrorResponse 형식)
    assert "not found" in response.json()["message"].lower()


@pytest.mark.e2e
def test_get_all_schedules_e2e(e2e_client):
    """HTTP를 통한 날짜 범위 기반 일정 조회 E2E 테스트"""
    # 1. 여러 일정 생성
    schedule_ids = []
    for i in range(3):
        create_response = e2e_client.post(
            "/v1/schedules",
            json={
                "title": f"일정 {i}",
                "start_time": f"2024-01-01T{10 + i:02d}:00:00Z",
                "end_time": f"2024-01-01T{12 + i:02d}:00:00Z",
            },
        )
        schedule_ids.append(create_response.json()["id"])

    # 2. 날짜 범위로 일정 조회
    response = e2e_client.get(
        "/v1/schedules",
        params={
            "start_date": "2024-01-01T00:00:00Z",
            "end_date": "2024-01-01T23:59:59Z"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 3

    # 생성한 일정들이 모두 포함되어 있는지 확인
    returned_ids = [s["id"] for s in data]
    for schedule_id in schedule_ids:
        assert schedule_id in returned_ids


@pytest.mark.e2e
def test_update_schedule_e2e(e2e_client):
    """HTTP를 통한 일정 업데이트 E2E 테스트"""
    # 1. 일정 생성
    create_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "원본 제목",
            "description": "원본 설명",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    assert create_response.status_code == 201
    schedule_id = create_response.json()["id"]

    # 2. 일정 업데이트
    update_response = e2e_client.patch(
        f"/v1/schedules/{schedule_id}",
        json={
            "title": "업데이트된 제목",
            "description": "업데이트된 설명",
        },
    )
    assert update_response.status_code == 200
    updated_data = update_response.json()
    assert updated_data["title"] == "업데이트된 제목"
    assert updated_data["description"] == "업데이트된 설명"

    # 3. 업데이트 확인
    get_response = e2e_client.get(f"/v1/schedules/{schedule_id}")
    assert get_response.status_code == 200
    assert get_response.json()["title"] == "업데이트된 제목"


@pytest.mark.e2e
def test_delete_schedule_e2e(e2e_client):
    """HTTP를 통한 일정 삭제 E2E 테스트"""
    # 1. 일정 생성
    create_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "삭제 테스트 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    assert create_response.status_code == 201
    schedule_id = create_response.json()["id"]

    # 2. 일정 삭제
    delete_response = e2e_client.delete(f"/v1/schedules/{schedule_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["ok"] is True

    # 3. 삭제 확인
    get_response = e2e_client.get(f"/v1/schedules/{schedule_id}")
    assert get_response.status_code == 404


@pytest.mark.e2e
def test_schedule_flow_e2e(e2e_client):
    """HTTP를 통한 일정 전체 흐름 E2E 테스트"""
    # 1. 일정 생성
    create_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "전체 흐름 테스트",
            "description": "초기 설명",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    assert create_response.status_code == 201
    schedule_data = create_response.json()
    schedule_id = schedule_data["id"]
    assert schedule_data["title"] == "전체 흐름 테스트"

    # 2. 일정 조회
    get_response = e2e_client.get(f"/v1/schedules/{schedule_id}")
    assert get_response.status_code == 200
    assert get_response.json()["title"] == "전체 흐름 테스트"

    # 3. 일정 업데이트
    update_response = e2e_client.patch(
        f"/v1/schedules/{schedule_id}",
        json={
            "title": "업데이트된 전체 흐름",
            "description": "업데이트된 설명",
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["title"] == "업데이트된 전체 흐름"

    # 4. 최종 상태 확인
    final_response = e2e_client.get(f"/v1/schedules/{schedule_id}")
    assert final_response.status_code == 200
    final_data = final_response.json()
    assert final_data["title"] == "업데이트된 전체 흐름"
    assert final_data["description"] == "업데이트된 설명"

    # 5. 일정 삭제
    delete_response = e2e_client.delete(f"/v1/schedules/{schedule_id}")
    assert delete_response.status_code == 200

    # 6. 삭제 확인
    deleted_response = e2e_client.get(f"/v1/schedules/{schedule_id}")
    assert deleted_response.status_code == 404


@pytest.mark.e2e
def test_create_schedule_invalid_time_e2e(e2e_client):
    """잘못된 시간으로 일정 생성 실패 E2E 테스트"""
    response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "잘못된 시간 테스트",
            "start_time": "2024-01-01T12:00:00Z",
            "end_time": "2024-01-01T10:00:00Z",  # end_time < start_time
        },
    )

    # Pydantic validation이 실패해야 함
    assert response.status_code == 422


@pytest.mark.e2e
def test_create_schedule_with_timezone_e2e(e2e_client):
    """타임존 변환을 포함한 일정 생성 E2E 테스트"""
    # UTC로 일정 생성
    response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "타임존 테스트 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
        params={"timezone": "Asia/Seoul"},
    )

    assert response.status_code == 201
    data = response.json()

    # 타임존이 변환되어야 함 (UTC 10:00 -> KST 19:00)
    # Python의 strftime %z는 +0900 형식(콜론 없음)을 생성
    start_time = data["start_time"]
    assert "+0900" in start_time or start_time.endswith("+0900")
    # 시간이 19:00으로 변환되었는지 확인
    assert "19:00:00" in start_time

    # created_at도 타임존 변환되어야 함
    created_at = data["created_at"]
    assert "+0900" in created_at or created_at.endswith("+0900")


@pytest.mark.e2e
def test_get_schedule_with_timezone_e2e(e2e_client):
    """타임존 변환을 포함한 일정 조회 E2E 테스트"""
    # 1. 일정 생성 (UTC)
    create_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "타임존 조회 테스트",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    assert create_response.status_code == 201
    schedule_id = create_response.json()["id"]

    # 2. 타임존 없이 조회 (UTC 형식으로 직렬화, +0000)
    get_response_utc = e2e_client.get(f"/v1/schedules/{schedule_id}")
    assert get_response_utc.status_code == 200
    utc_data = get_response_utc.json()
    # UTC 형식으로 직렬화됨 (+0000)
    assert "+0000" in utc_data["start_time"] or utc_data["start_time"].endswith("+0000")
    # 원본 시간 값이 유지되어야 함
    assert "10:00:00" in utc_data["start_time"]

    # 3. Asia/Seoul 타임존으로 조회
    get_response_kst = e2e_client.get(
        f"/v1/schedules/{schedule_id}",
        params={"timezone": "Asia/Seoul"}
    )
    assert get_response_kst.status_code == 200
    kst_data = get_response_kst.json()
    # KST로 변환되어야 함 (+0900 형식, Python의 %z는 콜론 없음)
    assert "+0900" in kst_data["start_time"] or kst_data["start_time"].endswith("+0900")
    # 시간이 19:00으로 변환되었는지 확인 (UTC 10:00 + 9시간)
    assert "19:00:00" in kst_data["start_time"]

    # 4. +09:00 형식으로 조회
    get_response_offset = e2e_client.get(
        f"/v1/schedules/{schedule_id}",
        params={"timezone": "+09:00"}
    )
    assert get_response_offset.status_code == 200
    offset_data = get_response_offset.json()
    # +0900 형식으로 직렬화됨 (Python의 %z는 콜론 없음)
    assert "+0900" in offset_data["start_time"] or offset_data["start_time"].endswith("+0900")


@pytest.mark.e2e
def test_get_all_schedules_with_timezone_e2e(e2e_client):
    """타임존 변환을 포함한 날짜 범위 기반 일정 조회 E2E 테스트"""
    # 1. 일정 생성
    create_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "타임존 리스트 테스트",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    schedule_id = create_response.json()["id"]

    # 2. 타임존으로 날짜 범위 기반 일정 조회
    response = e2e_client.get(
        "/v1/schedules",
        params={
            "start_date": "2024-01-01T00:00:00Z",
            "end_date": "2024-01-01T23:59:59Z",
            "timezone": "Asia/Seoul"
        }
    )
    assert response.status_code == 200
    schedules = response.json()
    assert isinstance(schedules, list)
    assert len(schedules) > 0

    # 생성한 일정이 포함되어 있는지 확인
    schedule_ids = [s["id"] for s in schedules]
    assert schedule_id in schedule_ids

    # 모든 일정의 datetime 필드가 타임존 변환되어야 함
    # Python의 strftime %z는 +0900 형식(콜론 없음)을 생성
    for schedule in schedules:
        if schedule.get("start_time"):
            assert "+0900" in schedule["start_time"] or schedule["start_time"].endswith("+0900")


@pytest.mark.e2e
def test_update_schedule_with_timezone_e2e(e2e_client):
    """타임존 변환을 포함한 일정 업데이트 E2E 테스트"""
    # 1. 일정 생성
    create_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "타임존 업데이트 테스트",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        },
    )
    assert create_response.status_code == 201
    schedule_id = create_response.json()["id"]

    # 2. 타임존으로 업데이트
    update_response = e2e_client.patch(
        f"/v1/schedules/{schedule_id}",
        json={"title": "업데이트된 제목"},
        params={"timezone": "Asia/Seoul"},
    )
    assert update_response.status_code == 200
    data = update_response.json()
    assert data["title"] == "업데이트된 제목"
    # 타임존 변환 확인 (+0900 형식, Python의 %z는 콜론 없음)
    assert "+0900" in data["start_time"] or data["start_time"].endswith("+0900")


@pytest.mark.e2e
def test_create_schedule_with_tags_e2e(e2e_client):
    """태그를 포함한 일정 생성 E2E 테스트"""
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

    # 2. 태그를 포함한 일정 생성
    response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "태그 있는 일정",
            "description": "태그 테스트 설명",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
            "tag_ids": [tag1_id, tag2_id]
        }
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "태그 있는 일정"
    assert "id" in data
    assert "tags" in data
    assert len(data["tags"]) == 2

    # 태그 ID 확인
    tag_ids = [tag["id"] for tag in data["tags"]]
    assert tag1_id in tag_ids
    assert tag2_id in tag_ids

    # 태그 정보 확인
    for tag in data["tags"]:
        assert "id" in tag
        assert "name" in tag
        assert "color" in tag
        assert tag["name"] in ["중요", "긴급"]


@pytest.mark.e2e
def test_create_schedule_without_tags_e2e(e2e_client):
    """태그 없이 일정 생성 E2E 테스트"""
    response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "태그 없는 일정",
            "description": "태그 없이 생성",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        }
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "태그 없는 일정"
    assert "id" in data
    assert "tags" in data
    assert len(data["tags"]) == 0  # 태그가 없어야 함


@pytest.mark.e2e
def test_create_schedule_with_empty_tag_ids_e2e(e2e_client):
    """빈 tag_ids로 일정 생성 E2E 테스트"""
    response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "빈 태그 리스트 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
            "tag_ids": []
        }
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "빈 태그 리스트 일정"
    assert "tags" in data
    assert len(data["tags"]) == 0


@pytest.mark.e2e
def test_get_schedule_with_tags_e2e(e2e_client):
    """태그가 포함된 일정 조회 E2E 테스트"""
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

    # 2. 태그를 포함한 일정 생성
    create_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "조회 테스트 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
            "tag_ids": [tag_id]
        }
    )
    assert create_response.status_code == 201
    schedule_id = create_response.json()["id"]

    # 3. 일정 조회 및 태그 확인
    get_response = e2e_client.get(f"/v1/schedules/{schedule_id}")
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["id"] == schedule_id
    assert data["title"] == "조회 테스트 일정"
    assert "tags" in data
    assert len(data["tags"]) == 1
    assert data["tags"][0]["id"] == tag_id
    assert data["tags"][0]["name"] == "중요"


@pytest.mark.e2e
def test_update_schedule_tags_e2e(e2e_client):
    """일정 수정 시 태그 업데이트 E2E 테스트"""
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

    # 2. 태그 없이 일정 생성
    create_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "원본 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
        }
    )
    assert create_response.status_code == 201
    schedule_id = create_response.json()["id"]

    # 초기 태그 확인 (없어야 함)
    initial_response = e2e_client.get(f"/v1/schedules/{schedule_id}")
    assert len(initial_response.json()["tags"]) == 0

    # 3. 태그 추가 (수정)
    update_response = e2e_client.patch(
        f"/v1/schedules/{schedule_id}",
        json={"tag_ids": [tag1_id, tag2_id]}
    )
    assert update_response.status_code == 200
    updated_data = update_response.json()
    assert "tags" in updated_data
    assert len(updated_data["tags"]) == 2

    # 4. 태그 변경 (수정)
    update_response2 = e2e_client.patch(
        f"/v1/schedules/{schedule_id}",
        json={"tag_ids": [tag1_id]}  # tag1만 남김
    )
    assert update_response2.status_code == 200
    updated_data2 = update_response2.json()
    assert len(updated_data2["tags"]) == 1
    assert updated_data2["tags"][0]["id"] == tag1_id

    # 5. 태그 제거 (수정)
    update_response3 = e2e_client.patch(
        f"/v1/schedules/{schedule_id}",
        json={"tag_ids": []}  # 모든 태그 제거
    )
    assert update_response3.status_code == 200
    updated_data3 = update_response3.json()
    assert len(updated_data3["tags"]) == 0


@pytest.mark.e2e
def test_get_all_schedules_with_tag_filter_e2e(e2e_client):
    """태그 ID로 일정 필터링 E2E 테스트"""
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

    # 2. 여러 일정 생성 (다양한 태그 조합)
    schedule1_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "태그1과 태그2 모두 있는 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
            "tag_ids": [tag1_id, tag2_id]
        }
    )
    schedule1_id = schedule1_response.json()["id"]

    schedule2_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "태그1만 있는 일정",
            "start_time": "2024-01-02T10:00:00Z",
            "end_time": "2024-01-02T12:00:00Z",
            "tag_ids": [tag1_id]
        }
    )
    schedule2_id = schedule2_response.json()["id"]

    schedule3_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "태그 없는 일정",
            "start_time": "2024-01-03T10:00:00Z",
            "end_time": "2024-01-03T12:00:00Z",
        }
    )
    schedule3_id = schedule3_response.json()["id"]

    # 3. tag1으로 필터링 (AND 방식이므로 tag1만 있는 일정도 포함)
    filter_response = e2e_client.get(
        "/v1/schedules",
        params={
            "start_date": "2024-01-01T00:00:00Z",
            "end_date": "2024-01-03T23:59:59Z",
            "tag_ids": [tag1_id]
        }
    )
    assert filter_response.status_code == 200
    filtered_schedules = filter_response.json()
    schedule_ids = [s["id"] for s in filtered_schedules]
    assert schedule1_id in schedule_ids  # tag1과 tag2 모두 있음
    assert schedule2_id in schedule_ids  # tag1만 있음
    assert schedule3_id not in schedule_ids  # 태그 없음

    # 4. tag1 AND tag2로 필터링 (둘 다 있어야 함)
    filter_response2 = e2e_client.get(
        "/v1/schedules",
        params={
            "start_date": "2024-01-01T00:00:00Z",
            "end_date": "2024-01-03T23:59:59Z",
            "tag_ids": [tag1_id, tag2_id]
        }
    )
    assert filter_response2.status_code == 200
    filtered_schedules2 = filter_response2.json()
    schedule_ids2 = [s["id"] for s in filtered_schedules2]
    assert schedule1_id in schedule_ids2  # tag1과 tag2 모두 있음
    assert schedule2_id not in schedule_ids2  # tag1만 있음
    assert schedule3_id not in schedule_ids2  # 태그 없음


@pytest.mark.e2e
def test_get_all_schedules_with_group_filter_e2e(e2e_client):
    """태그 그룹 ID로 일정 필터링 E2E 테스트"""
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

    # 2. 여러 일정 생성 (다양한 그룹의 태그)
    schedule1_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "업무 그룹 태그 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
            "tag_ids": [tag1_id]  # 업무 그룹
        }
    )
    schedule1_id = schedule1_response.json()["id"]

    schedule2_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "개인 그룹 태그 일정",
            "start_time": "2024-01-02T10:00:00Z",
            "end_time": "2024-01-02T12:00:00Z",
            "tag_ids": [tag3_id]  # 개인 그룹
        }
    )
    schedule2_id = schedule2_response.json()["id"]

    schedule3_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "태그 없는 일정",
            "start_time": "2024-01-03T10:00:00Z",
            "end_time": "2024-01-03T12:00:00Z",
        }
    )
    schedule3_id = schedule3_response.json()["id"]

    # 3. 업무 그룹으로 필터링
    filter_response = e2e_client.get(
        "/v1/schedules",
        params={
            "start_date": "2024-01-01T00:00:00Z",
            "end_date": "2024-01-03T23:59:59Z",
            "group_ids": [group1_id]
        }
    )
    assert filter_response.status_code == 200
    filtered_schedules = filter_response.json()
    schedule_ids = [s["id"] for s in filtered_schedules]
    assert schedule1_id in schedule_ids  # 업무 그룹 태그 있음
    assert schedule2_id not in schedule_ids  # 개인 그룹 태그만 있음
    assert schedule3_id not in schedule_ids  # 태그 없음

    # 4. 개인 그룹으로 필터링
    filter_response2 = e2e_client.get(
        "/v1/schedules",
        params={
            "start_date": "2024-01-01T00:00:00Z",
            "end_date": "2024-01-03T23:59:59Z",
            "group_ids": [group2_id]
        }
    )
    assert filter_response2.status_code == 200
    filtered_schedules2 = filter_response2.json()
    schedule_ids2 = [s["id"] for s in filtered_schedules2]
    assert schedule1_id not in schedule_ids2  # 업무 그룹 태그만 있음
    assert schedule2_id in schedule_ids2  # 개인 그룹 태그 있음
    assert schedule3_id not in schedule_ids2  # 태그 없음


@pytest.mark.e2e
def test_get_all_schedules_with_tag_and_group_filter_e2e(e2e_client):
    """태그 ID와 그룹 ID 조합 필터링 E2E 테스트"""
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

    # 2. 여러 일정 생성
    schedule1_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "업무 그룹 태그1 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
            "tag_ids": [tag1_id]  # 업무 그룹, tag1
        }
    )
    schedule1_id = schedule1_response.json()["id"]

    schedule2_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "업무 그룹 태그2 일정",
            "start_time": "2024-01-02T10:00:00Z",
            "end_time": "2024-01-02T12:00:00Z",
            "tag_ids": [tag2_id]  # 업무 그룹, tag2
        }
    )
    schedule2_id = schedule2_response.json()["id"]

    schedule3_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "개인 그룹 태그 일정",
            "start_time": "2024-01-03T10:00:00Z",
            "end_time": "2024-01-03T12:00:00Z",
            "tag_ids": [tag3_id]  # 개인 그룹
        }
    )
    schedule3_id = schedule3_response.json()["id"]

    # 3. tag1 AND 업무 그룹 필터링
    filter_response = e2e_client.get(
        "/v1/schedules",
        params={
            "start_date": "2024-01-01T00:00:00Z",
            "end_date": "2024-01-03T23:59:59Z",
            "tag_ids": [tag1_id],
            "group_ids": [group1_id]
        }
    )
    assert filter_response.status_code == 200
    filtered_schedules = filter_response.json()
    schedule_ids = [s["id"] for s in filtered_schedules]
    assert schedule1_id in schedule_ids  # tag1과 업무 그룹 모두 만족
    assert schedule2_id not in schedule_ids  # tag1 없음
    assert schedule3_id not in schedule_ids  # 개인 그룹


@pytest.mark.e2e
def test_get_all_schedules_without_tag_filter_e2e(e2e_client):
    """태그 필터링 없이 모든 일정 조회 E2E 테스트"""
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

    # 2. 태그 있는 일정과 태그 없는 일정 생성
    schedule1_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "태그 있는 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
            "tag_ids": [tag_id]
        }
    )
    schedule1_id = schedule1_response.json()["id"]

    schedule2_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "태그 없는 일정",
            "start_time": "2024-01-02T10:00:00Z",
            "end_time": "2024-01-02T12:00:00Z",
        }
    )
    schedule2_id = schedule2_response.json()["id"]

    # 3. 필터링 없이 날짜 범위로 일정 조회
    response = e2e_client.get(
        "/v1/schedules",
        params={
            "start_date": "2024-01-01T00:00:00Z",
            "end_date": "2024-01-02T23:59:59Z"
        }
    )
    assert response.status_code == 200
    schedules = response.json()
    schedule_ids = [s["id"] for s in schedules]
    assert schedule1_id in schedule_ids  # 태그 있는 일정 포함
    assert schedule2_id in schedule_ids  # 태그 없는 일정도 포함


@pytest.mark.e2e
def test_get_recurring_schedules_e2e(e2e_client):
    """반복 일정 조회 E2E 테스트 (가상 인스턴스 확장)"""
    # 1. 주간 반복 일정 생성 (매주 월요일, 4주간)
    create_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "주간 회의",
            "start_time": "2024-01-01T10:00:00Z",  # 2024-01-01은 월요일
            "end_time": "2024-01-01T12:00:00Z",
            "recurrence_rule": "FREQ=WEEKLY;BYDAY=MO",
            "recurrence_end": "2024-01-29T23:59:59Z",  # 4주간
        },
    )
    assert create_response.status_code == 201
    parent_schedule_id = create_response.json()["id"]

    # 2. 날짜 범위로 조회 (1월 전체)
    response = e2e_client.get(
        "/v1/schedules",
        params={
            "start_date": "2024-01-01T00:00:00Z",
            "end_date": "2024-01-31T23:59:59Z"
        }
    )
    assert response.status_code == 200
    schedules = response.json()

    # 반복 일정이 가상 인스턴스로 확장되어야 함
    recurring_instances = [
        s for s in schedules
        if s.get("parent_id") == parent_schedule_id
    ]
    assert len(recurring_instances) == 5  # 1월의 5개 월요일

    # 각 인스턴스가 고유 ID를 가져야 함
    instance_ids = {s["id"] for s in recurring_instances}
    assert len(instance_ids) == 5  # 모두 다른 ID

    # 각 인스턴스의 시작 시간이 월요일이어야 함
    for instance in recurring_instances:
        from datetime import datetime
        start_time = datetime.fromisoformat(instance["start_time"].replace("Z", "+00:00"))
        assert start_time.weekday() == 0  # 월요일
        assert instance["parent_id"] == parent_schedule_id
        assert instance.get("recurrence_rule") is None  # 가상 인스턴스는 반복 규칙 없음


@pytest.mark.e2e
def test_get_recurring_schedules_with_date_range_filter_e2e(e2e_client):
    """반복 일정 날짜 범위 필터링 E2E 테스트"""
    # 1. 일일 반복 일정 생성 (10일간)
    create_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "일일 회의",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
            "recurrence_rule": "FREQ=DAILY",
            "recurrence_end": "2024-01-10T23:59:59Z",
        },
    )
    assert create_response.status_code == 201
    parent_schedule_id = create_response.json()["id"]

    # 2. 1월 5일부터 7일까지만 조회
    response = e2e_client.get(
        "/v1/schedules",
        params={
            "start_date": "2024-01-05T00:00:00Z",
            "end_date": "2024-01-07T23:59:59Z"
        }
    )
    assert response.status_code == 200
    schedules = response.json()

    recurring_instances = [
        s for s in schedules
        if s.get("parent_id") == parent_schedule_id
    ]
    assert len(recurring_instances) == 3  # 5일, 6일, 7일

    # 각 인스턴스의 날짜 확인
    from datetime import datetime
    dates = {
        datetime.fromisoformat(s["start_time"].replace("Z", "+00:00")).date()
        for s in recurring_instances
    }
    expected_dates = {
        datetime(2024, 1, 5).date(),
        datetime(2024, 1, 6).date(),
        datetime(2024, 1, 7).date(),
    }
    assert dates == expected_dates


@pytest.mark.e2e
def test_get_recurring_schedules_mixed_with_regular_e2e(e2e_client):
    """반복 일정과 일반 일정이 함께 조회되는지 E2E 테스트"""
    # 1. 일반 일정 생성
    regular_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "일반 일정",
            "start_time": "2024-01-05T10:00:00Z",
            "end_time": "2024-01-05T12:00:00Z",
        },
    )
    assert regular_response.status_code == 201
    regular_schedule_id = regular_response.json()["id"]

    # 2. 반복 일정 생성
    recurring_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "반복 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
            "recurrence_rule": "FREQ=DAILY",
            "recurrence_end": "2024-01-10T23:59:59Z",
        },
    )
    assert recurring_response.status_code == 201
    parent_schedule_id = recurring_response.json()["id"]

    # 3. 1월 5일 조회
    response = e2e_client.get(
        "/v1/schedules",
        params={
            "start_date": "2024-01-05T00:00:00Z",
            "end_date": "2024-01-05T23:59:59Z"
        }
    )
    assert response.status_code == 200
    schedules = response.json()

    # 일반 일정 1개 + 반복 일정 인스턴스 1개
    regular_schedules = [s for s in schedules if s["id"] == regular_schedule_id]
    recurring_instances = [
        s for s in schedules
        if s.get("parent_id") == parent_schedule_id
    ]

    assert len(regular_schedules) == 1
    assert len(recurring_instances) == 1


# ==================== Schedule -> Todo 생성 E2E 테스트 ====================

@pytest.mark.e2e
def test_create_schedule_with_todo_options_e2e(e2e_client):
    """Schedule 생성 시 create_todo_options로 Todo 동시 생성 E2E 테스트"""
    # 1. 태그 그룹 생성
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={
            "name": "Schedule Todo 테스트 그룹",
            "color": "#FF5733",
        }
    )
    assert group_response.status_code == 201
    group_id = group_response.json()["id"]

    # 2. create_todo_options와 함께 Schedule 생성
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "Todo와 함께 생성할 일정",
            "description": "설명입니다",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
            "create_todo_options": {
                "tag_group_id": group_id
            }
        }
    )
    assert schedule_response.status_code == 201
    schedule = schedule_response.json()

    # Schedule에 source_todo_id가 설정되어야 함
    assert schedule["source_todo_id"] is not None

    # 3. 생성된 Todo 확인
    todo_response = e2e_client.get(f"/v1/todos/{schedule['source_todo_id']}")
    assert todo_response.status_code == 200
    todo = todo_response.json()

    assert todo["title"] == "Todo와 함께 생성할 일정"
    assert todo["description"] == "설명입니다"
    assert todo["tag_group_id"] == group_id


@pytest.mark.e2e
def test_create_todo_from_schedule_e2e(e2e_client):
    """기존 Schedule에서 Todo 생성 E2E 테스트"""
    # 1. 태그 그룹 생성
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={
            "name": "Schedule To Todo 테스트",
            "color": "#00FF00",
        }
    )
    assert group_response.status_code == 201
    group_id = group_response.json()["id"]

    # 2. Schedule 생성 (Todo 없이)
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "나중에 Todo로 변환할 일정",
            "description": "변환 테스트",
            "start_time": "2024-02-01T14:00:00Z",
            "end_time": "2024-02-01T16:00:00Z",
        }
    )
    assert schedule_response.status_code == 201
    schedule_id = schedule_response.json()["id"]

    # 3. Schedule에서 Todo 생성
    todo_response = e2e_client.post(
        f"/v1/schedules/{schedule_id}/todo",
        params={"tag_group_id": group_id}
    )
    assert todo_response.status_code == 201
    todo = todo_response.json()

    assert todo["title"] == "나중에 Todo로 변환할 일정"
    assert todo["description"] == "변환 테스트"
    assert todo["tag_group_id"] == group_id
    assert todo["status"] == "SCHEDULED"

    # 4. Schedule 확인 - source_todo_id가 설정되어야 함
    schedule_check = e2e_client.get(f"/v1/schedules/{schedule_id}")
    assert schedule_check.status_code == 200
    assert schedule_check.json()["source_todo_id"] == todo["id"]


@pytest.mark.e2e
def test_create_todo_from_schedule_already_linked_e2e(e2e_client):
    """이미 Todo와 연결된 Schedule에서 다시 Todo 생성 시 에러 E2E 테스트"""
    # 1. 태그 그룹 생성
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={
            "name": "중복 테스트 그룹",
            "color": "#0000FF",
        }
    )
    assert group_response.status_code == 201
    group_id = group_response.json()["id"]

    # 2. Schedule 생성 (Todo 없이)
    schedule_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "중복 연결 테스트 일정",
            "start_time": "2024-03-01T10:00:00Z",
            "end_time": "2024-03-01T12:00:00Z",
        }
    )
    assert schedule_response.status_code == 201
    schedule_id = schedule_response.json()["id"]

    # 3. 첫 번째 Todo 생성 - 성공
    first_todo_response = e2e_client.post(
        f"/v1/schedules/{schedule_id}/todo",
        params={"tag_group_id": group_id}
    )
    assert first_todo_response.status_code == 201

    # 4. 두 번째 Todo 생성 시도 - 에러
    second_todo_response = e2e_client.post(
        f"/v1/schedules/{schedule_id}/todo",
        params={"tag_group_id": group_id}
    )
    assert second_todo_response.status_code == 400
    assert "already linked" in second_todo_response.json()["message"].lower()


# ============================================================
# 일정 복합 필터링 E2E 테스트
# ============================================================

@pytest.mark.e2e
def test_get_schedules_with_timezone_and_tag_filter_e2e(e2e_client):
    """타임존 + 태그 필터 복합 조회 E2E 테스트"""
    # 1. 태그 그룹 및 태그 생성
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "복합필터 테스트", "color": "#FF5733"}
    )
    group_id = group_response.json()["id"]

    tag_response = e2e_client.post(
        "/v1/tags",
        json={"name": "중요", "color": "#FF0000", "group_id": group_id}
    )
    tag_id = tag_response.json()["id"]

    # 2. 태그가 있는 일정 생성
    tagged_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "태그 있는 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
            "tag_ids": [tag_id],
        }
    )
    tagged_id = tagged_response.json()["id"]

    # 3. 태그 없는 일정 생성
    untagged_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "태그 없는 일정",
            "start_time": "2024-01-01T14:00:00Z",
            "end_time": "2024-01-01T16:00:00Z",
        }
    )
    untagged_id = untagged_response.json()["id"]

    # 4. 타임존 + 태그 필터로 조회
    response = e2e_client.get(
        "/v1/schedules",
        params={
            "start_date": "2024-01-01T00:00:00Z",
            "end_date": "2024-01-01T23:59:59Z",
            "tag_ids": [tag_id],
            "timezone": "Asia/Seoul",
        }
    )
    assert response.status_code == 200
    schedules = response.json()

    # 태그 필터링 확인
    schedule_ids = [s["id"] for s in schedules]
    assert tagged_id in schedule_ids
    assert untagged_id not in schedule_ids

    # 타임존 변환 확인
    tagged_schedule = next(s for s in schedules if s["id"] == tagged_id)
    assert "+0900" in tagged_schedule["start_time"]
    # UTC 10:00 -> KST 19:00
    assert "19:00:00" in tagged_schedule["start_time"]


@pytest.mark.e2e
def test_get_schedules_with_timezone_and_group_filter_e2e(e2e_client):
    """타임존 + 그룹 필터 복합 조회 E2E 테스트"""
    # 1. 태그 그룹 생성
    group1_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "그룹1", "color": "#FF5733"}
    )
    group1_id = group1_response.json()["id"]

    group2_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "그룹2", "color": "#00FF00"}
    )
    group2_id = group2_response.json()["id"]

    # 2. 태그 생성
    tag1_response = e2e_client.post(
        "/v1/tags",
        json={"name": "태그1", "color": "#FF0000", "group_id": group1_id}
    )
    tag1_id = tag1_response.json()["id"]

    tag2_response = e2e_client.post(
        "/v1/tags",
        json={"name": "태그2", "color": "#0000FF", "group_id": group2_id}
    )
    tag2_id = tag2_response.json()["id"]

    # 3. 일정 생성
    schedule1_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "그룹1 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
            "tag_ids": [tag1_id],
        }
    )
    schedule1_id = schedule1_response.json()["id"]

    schedule2_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "그룹2 일정",
            "start_time": "2024-01-01T14:00:00Z",
            "end_time": "2024-01-01T16:00:00Z",
            "tag_ids": [tag2_id],
        }
    )
    schedule2_id = schedule2_response.json()["id"]

    # 4. 그룹1 + 타임존으로 조회
    response = e2e_client.get(
        "/v1/schedules",
        params={
            "start_date": "2024-01-01T00:00:00Z",
            "end_date": "2024-01-01T23:59:59Z",
            "group_ids": [group1_id],
            "timezone": "+09:00",
        }
    )
    assert response.status_code == 200
    schedules = response.json()

    # 그룹 필터링 확인
    schedule_ids = [s["id"] for s in schedules]
    assert schedule1_id in schedule_ids
    assert schedule2_id not in schedule_ids

    # 타임존 변환 확인
    schedule1 = next(s for s in schedules if s["id"] == schedule1_id)
    assert "+0900" in schedule1["start_time"]


@pytest.mark.e2e
def test_get_schedules_empty_result_with_filter_e2e(e2e_client):
    """필터 조건에 맞는 일정이 없을 때 빈 배열 반환 E2E 테스트"""
    from uuid import uuid4

    # 존재하지 않는 태그 ID로 조회
    fake_tag_id = str(uuid4())
    response = e2e_client.get(
        "/v1/schedules",
        params={
            "start_date": "2024-01-01T00:00:00Z",
            "end_date": "2024-01-01T23:59:59Z",
            "tag_ids": [fake_tag_id],
        }
    )
    assert response.status_code == 200
    schedules = response.json()
    assert isinstance(schedules, list)
    assert len(schedules) == 0


@pytest.mark.e2e
def test_get_schedules_with_multiple_tag_and_group_filter_e2e(e2e_client):
    """복수 태그 + 복수 그룹 필터 E2E 테스트"""
    # 1. 태그 그룹 생성
    group_response = e2e_client.post(
        "/v1/tags/groups",
        json={"name": "복합필터 그룹", "color": "#FF5733"}
    )
    group_id = group_response.json()["id"]

    # 2. 태그 여러 개 생성
    tag1_response = e2e_client.post(
        "/v1/tags",
        json={"name": "태그A", "color": "#FF0000", "group_id": group_id}
    )
    tag1_id = tag1_response.json()["id"]

    tag2_response = e2e_client.post(
        "/v1/tags",
        json={"name": "태그B", "color": "#00FF00", "group_id": group_id}
    )
    tag2_id = tag2_response.json()["id"]

    tag3_response = e2e_client.post(
        "/v1/tags",
        json={"name": "태그C", "color": "#0000FF", "group_id": group_id}
    )
    tag3_id = tag3_response.json()["id"]

    # 3. 일정 생성 (다양한 태그 조합)
    # 태그A, 태그B 모두 있는 일정
    schedule_ab_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "태그AB 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
            "tag_ids": [tag1_id, tag2_id],
        }
    )
    schedule_ab_id = schedule_ab_response.json()["id"]

    # 태그A만 있는 일정
    schedule_a_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "태그A 일정",
            "start_time": "2024-01-01T14:00:00Z",
            "end_time": "2024-01-01T16:00:00Z",
            "tag_ids": [tag1_id],
        }
    )
    schedule_a_id = schedule_a_response.json()["id"]

    # 태그C만 있는 일정
    schedule_c_response = e2e_client.post(
        "/v1/schedules",
        json={
            "title": "태그C 일정",
            "start_time": "2024-01-01T18:00:00Z",
            "end_time": "2024-01-01T20:00:00Z",
            "tag_ids": [tag3_id],
        }
    )
    schedule_c_id = schedule_c_response.json()["id"]

    # 4. 태그A AND 태그B 필터 (둘 다 있는 일정만)
    response = e2e_client.get(
        "/v1/schedules",
        params={
            "start_date": "2024-01-01T00:00:00Z",
            "end_date": "2024-01-01T23:59:59Z",
            "tag_ids": [tag1_id, tag2_id],
            "group_ids": [group_id],
        }
    )
    assert response.status_code == 200
    schedules = response.json()
    schedule_ids = [s["id"] for s in schedules]

    # 태그A, 태그B 모두 있는 일정만 반환
    assert schedule_ab_id in schedule_ids
    assert schedule_a_id not in schedule_ids  # 태그B 없음
    assert schedule_c_id not in schedule_ids  # 태그A, 태그B 없음


# ============================================================================
# Visibility & Scope E2E Tests (공유 기능)
# ============================================================================

@pytest.mark.e2e
def test_schedule_visibility_friends_scope_shared(multi_user_e2e):
    """친구에게 공유된 일정이 scope=shared로 조회되는지 E2E 테스트"""
    client_a = multi_user_e2e.as_user("user-a")
    client_b = multi_user_e2e.as_user("user-b")

    # 1. user-a가 친구에게 공개된 일정 생성
    schedule_response = client_a.post(
        "/v1/schedules",
        json={
            "title": "친구 공개 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
            "visibility": {
                "level": "friends",
            },
        },
    )
    assert schedule_response.status_code == 201
    schedule_id = schedule_response.json()["id"]

    # 2. user-a가 user-b에게 친구 요청
    friend_request = client_a.post(
        "/v1/friends/requests",
        json={"addressee_id": multi_user_e2e.get_user("user-b").sub}
    )
    assert friend_request.status_code == 201

    # 3. user-b가 친구 요청 수락
    # 수신된 요청 조회
    pending_response = client_b.get("/v1/friends/requests/received")
    assert pending_response.status_code == 200
    pending_list = pending_response.json()
    assert len(pending_list) > 0
    friendship_id = pending_list[0]["id"]

    # 친구 수락
    accept_response = client_b.post(f"/v1/friends/requests/{friendship_id}/accept")
    assert accept_response.status_code == 200

    # 4. user-b가 scope=shared로 일정 조회 시 일정 포함되는지 확인
    shared_response = client_b.get(
        "/v1/schedules",
        params={
            "start_date": "2024-01-01T00:00:00Z",
            "end_date": "2024-01-01T23:59:59Z",
            "scope": "shared",
        }
    )
    assert shared_response.status_code == 200
    shared_schedules = shared_response.json()
    shared_ids = [s["id"] for s in shared_schedules]
    assert schedule_id in shared_ids, "친구 공개 일정이 scope=shared에 포함되어야 함"

    # is_shared=True 확인
    shared_schedule = next(s for s in shared_schedules if s["id"] == schedule_id)
    assert shared_schedule["is_shared"] is True
    assert shared_schedule["owner_id"] == multi_user_e2e.get_user("user-a").sub


@pytest.mark.e2e
def test_schedule_visibility_friends_single_item_access(multi_user_e2e):
    """친구가 공유된 일정을 단건 조회할 수 있는지 E2E 테스트"""
    client_a = multi_user_e2e.as_user("user-a")
    client_b = multi_user_e2e.as_user("user-b")

    # 1. user-a가 친구에게 공개된 일정 생성
    schedule_response = client_a.post(
        "/v1/schedules",
        json={
            "title": "친구 공개 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
            "visibility": {
                "level": "friends",
            },
        },
    )
    assert schedule_response.status_code == 201
    schedule_id = schedule_response.json()["id"]

    # 2. 친구 관계 생성
    client_a.post("/v1/friends/requests", json={"addressee_id": multi_user_e2e.get_user("user-b").sub})
    pending_response = client_b.get("/v1/friends/requests/received")
    friendship_id = pending_response.json()[0]["id"]
    client_b.post(f"/v1/friends/requests/{friendship_id}/accept")

    # 3. user-b가 단건 조회 성공
    get_response = client_b.get(f"/v1/schedules/{schedule_id}")
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["id"] == schedule_id
    assert data["is_shared"] is True


@pytest.mark.e2e
def test_schedule_visibility_non_friend_cannot_access(multi_user_e2e):
    """친구가 아닌 사용자는 친구 공개 일정에 접근 불가 E2E 테스트"""
    client_a = multi_user_e2e.as_user("user-a")
    client_c = multi_user_e2e.as_user("user-c")  # 친구 아님

    # 1. user-a가 친구에게 공개된 일정 생성
    schedule_response = client_a.post(
        "/v1/schedules",
        json={
            "title": "친구 공개 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
            "visibility": {
                "level": "friends",
            },
        },
    )
    assert schedule_response.status_code == 201
    schedule_id = schedule_response.json()["id"]

    # 2. user-c가 scope=shared로 조회 시 포함 안 됨
    shared_response = client_c.get(
        "/v1/schedules",
        params={
            "start_date": "2024-01-01T00:00:00Z",
            "end_date": "2024-01-01T23:59:59Z",
            "scope": "shared",
        }
    )
    assert shared_response.status_code == 200
    shared_ids = [s["id"] for s in shared_response.json()]
    assert schedule_id not in shared_ids

    # 3. user-c가 단건 조회 시 403
    get_response = client_c.get(f"/v1/schedules/{schedule_id}")
    assert get_response.status_code == 403


@pytest.mark.e2e
def test_schedule_visibility_selected_friends(multi_user_e2e):
    """선택된 친구에게만 공유되는 일정 E2E 테스트"""
    client_a = multi_user_e2e.as_user("user-a")
    client_b = multi_user_e2e.as_user("user-b")
    client_c = multi_user_e2e.as_user("user-c")

    user_b_id = multi_user_e2e.get_user("user-b").sub
    user_c_id = multi_user_e2e.get_user("user-c").sub

    # 1. user-a ↔ user-b, user-c 친구 관계 생성
    client_a.post("/v1/friends/requests", json={"addressee_id": user_b_id})
    pending_b = client_b.get("/v1/friends/requests/received")
    client_b.post(f"/v1/friends/requests/{pending_b.json()[0]['id']}/accept")

    client_a.post("/v1/friends/requests", json={"addressee_id": user_c_id})
    pending_c = client_c.get("/v1/friends/requests/received")
    client_c.post(f"/v1/friends/requests/{pending_c.json()[0]['id']}/accept")

    # 2. user-a가 user-b에게만 공개된 일정 생성
    schedule_response = client_a.post(
        "/v1/schedules",
        json={
            "title": "선택 친구 공개 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
            "visibility": {
                "level": "selected",
                "allowed_user_ids": [user_b_id],
            },
        },
    )
    assert schedule_response.status_code == 201
    schedule_id = schedule_response.json()["id"]

    # 3. user-b는 scope=shared로 볼 수 있음
    shared_b = client_b.get(
        "/v1/schedules",
        params={
            "start_date": "2024-01-01T00:00:00Z",
            "end_date": "2024-01-01T23:59:59Z",
            "scope": "shared",
        }
    )
    shared_b_ids = [s["id"] for s in shared_b.json()]
    assert schedule_id in shared_b_ids

    # 4. user-c는 친구지만 allowlist에 없어서 볼 수 없음
    shared_c = client_c.get(
        "/v1/schedules",
        params={
            "start_date": "2024-01-01T00:00:00Z",
            "end_date": "2024-01-01T23:59:59Z",
            "scope": "shared",
        }
    )
    shared_c_ids = [s["id"] for s in shared_c.json()]
    assert schedule_id not in shared_c_ids


@pytest.mark.e2e
def test_schedule_visibility_public(multi_user_e2e):
    """전체 공개 일정 E2E 테스트"""
    client_a = multi_user_e2e.as_user("user-a")
    client_c = multi_user_e2e.as_user("user-c")  # 친구 아님

    # 1. user-a가 전체 공개 일정 생성
    schedule_response = client_a.post(
        "/v1/schedules",
        json={
            "title": "전체 공개 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
            "visibility": {
                "level": "public",
            },
        },
    )
    assert schedule_response.status_code == 201
    schedule_id = schedule_response.json()["id"]

    # 2. 친구가 아닌 user-c도 scope=shared로 볼 수 있음
    shared_response = client_c.get(
        "/v1/schedules",
        params={
            "start_date": "2024-01-01T00:00:00Z",
            "end_date": "2024-01-01T23:59:59Z",
            "scope": "shared",
        }
    )
    shared_ids = [s["id"] for s in shared_response.json()]
    assert schedule_id in shared_ids

    # 3. 단건 조회도 성공
    get_response = client_c.get(f"/v1/schedules/{schedule_id}")
    assert get_response.status_code == 200


@pytest.mark.e2e
def test_schedule_scope_all(multi_user_e2e):
    """scope=all로 내 일정 + 공유 일정 모두 조회 E2E 테스트"""
    client_a = multi_user_e2e.as_user("user-a")
    client_b = multi_user_e2e.as_user("user-b")

    # 1. user-a가 공개 일정 생성
    schedule_a = client_a.post(
        "/v1/schedules",
        json={
            "title": "A의 공개 일정",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T12:00:00Z",
            "visibility": {"level": "public"},
        },
    )
    schedule_a_id = schedule_a.json()["id"]

    # 2. user-b가 자신의 일정 생성
    schedule_b = client_b.post(
        "/v1/schedules",
        json={
            "title": "B의 일정",
            "start_time": "2024-01-01T14:00:00Z",
            "end_time": "2024-01-01T16:00:00Z",
        },
    )
    schedule_b_id = schedule_b.json()["id"]

    # 3. user-b가 scope=all로 조회
    all_response = client_b.get(
        "/v1/schedules",
        params={
            "start_date": "2024-01-01T00:00:00Z",
            "end_date": "2024-01-01T23:59:59Z",
            "scope": "all",
        }
    )
    assert all_response.status_code == 200
    all_schedules = all_response.json()
    all_ids = [s["id"] for s in all_schedules]

    # 내 일정과 공유 일정 모두 포함
    assert schedule_a_id in all_ids  # 공유 일정
    assert schedule_b_id in all_ids  # 내 일정
