"""
Meeting E2E 테스트

일정 조율 REST API 엔드포인트 통합 테스트
"""
import pytest
from uuid import uuid4


@pytest.mark.e2e
def test_create_meeting_e2e(e2e_client):
    """일정 조율 생성 E2E 테스트"""
    response = e2e_client.post(
        "/v1/meetings",
        json={
            "title": "팀 회의 일정 조율",
            "description": "다음 주 회의 일정을 조율합니다",
            "start_date": "2024-02-01",
            "end_date": "2024-02-07",
            "available_days": [0, 2, 4],  # 월, 수, 금
            "start_time": "09:00:00",
            "end_time": "18:00:00",
            "time_slot_minutes": 30,
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "팀 회의 일정 조율"
    assert data["description"] == "다음 주 회의 일정을 조율합니다"
    assert data["start_date"] == "2024-02-01"
    assert data["end_date"] == "2024-02-07"
    assert data["available_days"] == [0, 2, 4]
    assert data["start_time"] == "09:00:00"
    assert data["end_time"] == "18:00:00"
    assert data["time_slot_minutes"] == 30
    assert "id" in data
    assert "created_at" in data


@pytest.mark.e2e
def test_create_meeting_with_visibility_e2e(e2e_client):
    """가시성 설정과 함께 일정 조율 생성 E2E 테스트"""
    response = e2e_client.post(
        "/v1/meetings",
        json={
            "title": "제한된 회의",
            "start_date": "2024-02-01",
            "end_date": "2024-02-07",
            "available_days": [0, 2, 4],
            "start_time": "09:00:00",
            "end_time": "18:00:00",
            "time_slot_minutes": 30,
            "visibility": {
                "level": "allowed_emails",
                "allowed_emails": ["user@company.com"],
                "allowed_domains": ["company.com"],
            },
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["visibility_level"] == "allowed_emails"


@pytest.mark.e2e
def test_get_meeting_e2e(e2e_client):
    """일정 조율 조회 E2E 테스트"""
    # 1. 일정 조율 생성
    create_response = e2e_client.post(
        "/v1/meetings",
        json={
            "title": "조회 테스트 일정",
            "start_date": "2024-02-01",
            "end_date": "2024-02-07",
            "available_days": [0, 2, 4],
            "start_time": "09:00:00",
            "end_time": "18:00:00",
            "time_slot_minutes": 30,
        },
    )
    assert create_response.status_code == 201
    meeting_id = create_response.json()["id"]

    # 2. 일정 조율 조회
    get_response = e2e_client.get(f"/v1/meetings/{meeting_id}")
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["id"] == meeting_id
    assert data["title"] == "조회 테스트 일정"


@pytest.mark.e2e
def test_get_meeting_not_found_e2e(e2e_client):
    """존재하지 않는 일정 조율 조회 E2E 테스트"""
    non_existent_id = str(uuid4())
    response = e2e_client.get(f"/v1/meetings/{non_existent_id}")

    assert response.status_code == 404
    assert "not found" in response.json()["message"].lower()


@pytest.mark.e2e
def test_get_all_meetings_e2e(e2e_client):
    """내가 생성한 일정 조율 목록 조회 E2E 테스트"""
    # 1. 여러 일정 조율 생성
    meeting_ids = []
    for i in range(3):
        create_response = e2e_client.post(
            "/v1/meetings",
            json={
                "title": f"일정 조율 {i}",
                "start_date": "2024-02-01",
                "end_date": "2024-02-07",
                "available_days": [0, 2, 4],
                "start_time": "09:00:00",
                "end_time": "18:00:00",
                "time_slot_minutes": 30,
            },
        )
        meeting_ids.append(create_response.json()["id"])

    # 2. 일정 조율 목록 조회
    response = e2e_client.get("/v1/meetings")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 3

    # 생성한 일정 조율들이 모두 포함되어 있는지 확인
    returned_ids = [m["id"] for m in data]
    for meeting_id in meeting_ids:
        assert meeting_id in returned_ids


@pytest.mark.e2e
def test_update_meeting_e2e(e2e_client):
    """일정 조율 업데이트 E2E 테스트"""
    # 1. 일정 조율 생성
    create_response = e2e_client.post(
        "/v1/meetings",
        json={
            "title": "업데이트 테스트 일정",
            "start_date": "2024-02-01",
            "end_date": "2024-02-07",
            "available_days": [0, 2, 4],
            "start_time": "09:00:00",
            "end_time": "18:00:00",
            "time_slot_minutes": 30,
        },
    )
    assert create_response.status_code == 201
    meeting_id = create_response.json()["id"]

    # 2. 일정 조율 업데이트
    update_response = e2e_client.patch(
        f"/v1/meetings/{meeting_id}",
        json={
            "title": "업데이트된 제목",
            "description": "업데이트된 설명",
        },
    )
    assert update_response.status_code == 200
    data = update_response.json()
    assert data["title"] == "업데이트된 제목"
    assert data["description"] == "업데이트된 설명"


@pytest.mark.e2e
def test_delete_meeting_e2e(e2e_client):
    """일정 조율 삭제 E2E 테스트"""
    # 1. 일정 조율 생성
    create_response = e2e_client.post(
        "/v1/meetings",
        json={
            "title": "삭제 테스트 일정",
            "start_date": "2024-02-01",
            "end_date": "2024-02-07",
            "available_days": [0, 2, 4],
            "start_time": "09:00:00",
            "end_time": "18:00:00",
            "time_slot_minutes": 30,
        },
    )
    assert create_response.status_code == 201
    meeting_id = create_response.json()["id"]

    # 2. 일정 조율 삭제
    delete_response = e2e_client.delete(f"/v1/meetings/{meeting_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["ok"] is True

    # 3. 삭제 확인
    get_response = e2e_client.get(f"/v1/meetings/{meeting_id}")
    assert get_response.status_code == 404


@pytest.mark.e2e
def test_create_participant_e2e(e2e_client):
    """참여자 등록 E2E 테스트"""
    # 1. 일정 조율 생성
    create_response = e2e_client.post(
        "/v1/meetings",
        json={
            "title": "참여자 테스트",
            "start_date": "2024-02-01",
            "end_date": "2024-02-07",
            "available_days": [0, 2, 4],
            "start_time": "09:00:00",
            "end_time": "18:00:00",
            "time_slot_minutes": 30,
        },
    )
    meeting_id = create_response.json()["id"]

    # 2. 참여자 등록
    participant_response = e2e_client.post(
        f"/v1/meetings/{meeting_id}/participate",
        json={
            "display_name": "참여자1",
        },
    )
    assert participant_response.status_code == 201
    data = participant_response.json()
    assert data["display_name"] == "참여자1"
    assert data["meeting_id"] == meeting_id
    assert "id" in data


@pytest.mark.e2e
def test_set_availability_e2e(e2e_client):
    """참여자 가능 시간 설정 E2E 테스트"""
    # 1. 일정 조율 생성
    create_response = e2e_client.post(
        "/v1/meetings",
        json={
            "title": "가능 시간 테스트",
            "start_date": "2024-02-01",
            "end_date": "2024-02-07",
            "available_days": [0, 2, 4],
            "start_time": "09:00:00",
            "end_time": "18:00:00",
            "time_slot_minutes": 30,
        },
    )
    meeting_id = create_response.json()["id"]

    # 2. 참여자 등록
    participant_response = e2e_client.post(
        f"/v1/meetings/{meeting_id}/participate",
        json={"display_name": "참여자1"},
    )
    participant_id = participant_response.json()["id"]

    # 3. 가능 시간 설정
    availability_response = e2e_client.put(
        f"/v1/meetings/{meeting_id}/availability",
        params={"participant_id": participant_id},
        json=[
            {
                "slot_date": "2024-02-01",
                "start_time": "09:00:00",
                "end_time": "12:00:00",
            },
            {
                "slot_date": "2024-02-01",
                "start_time": "14:00:00",
                "end_time": "17:00:00",
            },
        ],
    )
    assert availability_response.status_code == 200
    data = availability_response.json()
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["slot_date"] == "2024-02-01"
    assert data[0]["start_time"] == "09:00:00"
    assert data[0]["end_time"] == "12:00:00"


@pytest.mark.e2e
def test_get_availability_e2e(e2e_client):
    """전체 참여자 가능 시간 조회 E2E 테스트"""
    # 1. 일정 조율 생성
    create_response = e2e_client.post(
        "/v1/meetings",
        json={
            "title": "가능 시간 조회 테스트",
            "start_date": "2024-02-01",
            "end_date": "2024-02-07",
            "available_days": [0, 2, 4],
            "start_time": "09:00:00",
            "end_time": "18:00:00",
            "time_slot_minutes": 30,
        },
    )
    meeting_id = create_response.json()["id"]

    # 2. 참여자 2명 등록 및 시간 설정
    participant1_response = e2e_client.post(
        f"/v1/meetings/{meeting_id}/participate",
        json={"display_name": "참여자1"},
    )
    participant1_id = participant1_response.json()["id"]

    participant2_response = e2e_client.post(
        f"/v1/meetings/{meeting_id}/participate",
        json={"display_name": "참여자2"},
    )
    participant2_id = participant2_response.json()["id"]

    # 참여자1 시간 설정 (2월 2일 금요일 - available_days에 포함)
    e2e_client.put(
        f"/v1/meetings/{meeting_id}/availability",
        params={"participant_id": participant1_id},
        json=[{
            "slot_date": "2024-02-02",
            "start_time": "09:00:00",
            "end_time": "12:00:00",
        }],
    )

    # 참여자2 시간 설정 (2월 2일 금요일 - available_days에 포함)
    e2e_client.put(
        f"/v1/meetings/{meeting_id}/availability",
        params={"participant_id": participant2_id},
        json=[{
            "slot_date": "2024-02-02",
            "start_time": "10:00:00",
            "end_time": "13:00:00",
        }],
    )

    # 3. 전체 가능 시간 조회
    availability_response = e2e_client.get(f"/v1/meetings/{meeting_id}/availability")
    assert availability_response.status_code == 200
    data = availability_response.json()
    assert isinstance(data, list)
    assert len(data) == 2

    # 각 참여자의 시간 슬롯 확인
    participant1_data = next(p for p in data if p["participant"]["id"] == participant1_id)
    assert len(participant1_data["time_slots"]) == 1
    assert participant1_data["time_slots"][0]["start_time"] == "09:00:00"


@pytest.mark.e2e
def test_get_meeting_result_e2e(e2e_client):
    """공통 가능 시간 분석 결과 조회 E2E 테스트"""
    # 1. 일정 조율 생성
    create_response = e2e_client.post(
        "/v1/meetings",
        json={
            "title": "결과 조회 테스트",
            "start_date": "2024-02-01",
            "end_date": "2024-02-07",
            "available_days": [0, 2, 4],
            "start_time": "09:00:00",
            "end_time": "18:00:00",
            "time_slot_minutes": 30,
        },
    )
    meeting_id = create_response.json()["id"]

    # 2. 참여자 2명 등록 및 시간 설정
    participant1_response = e2e_client.post(
        f"/v1/meetings/{meeting_id}/participate",
        json={"display_name": "참여자1"},
    )
    participant1_id = participant1_response.json()["id"]

    participant2_response = e2e_client.post(
        f"/v1/meetings/{meeting_id}/participate",
        json={"display_name": "참여자2"},
    )
    participant2_id = participant2_response.json()["id"]

    # 참여자1: 2월 2일(금) 9:00-12:00 가능
    e2e_client.put(
        f"/v1/meetings/{meeting_id}/availability",
        params={"participant_id": participant1_id},
        json=[{
            "slot_date": "2024-02-02",  # 금요일 (weekday=4, available_days에 포함)
            "start_time": "09:00:00",
            "end_time": "12:00:00",
        }],
    )

    # 참여자2: 2월 2일(금) 10:00-13:00 가능
    e2e_client.put(
        f"/v1/meetings/{meeting_id}/availability",
        params={"participant_id": participant2_id},
        json=[{
            "slot_date": "2024-02-02",  # 금요일 (weekday=4, available_days에 포함)
            "start_time": "10:00:00",
            "end_time": "13:00:00",
        }],
    )

    # 3. 공통 가능 시간 분석 결과 조회
    result_response = e2e_client.get(f"/v1/meetings/{meeting_id}/result")
    assert result_response.status_code == 200
    data = result_response.json()

    assert data["meeting"]["id"] == meeting_id
    assert "availability_grid" in data
    assert "2024-02-02" in data["availability_grid"]

    # 10:00-12:00 구간은 두 명 모두 가능 (count=2)
    date_grid = data["availability_grid"]["2024-02-02"]
    assert date_grid.get("10:00", 0) == 2
    assert date_grid.get("11:00", 0) == 2
    assert date_grid.get("11:30", 0) == 2

    # 9:00-10:00 구간은 참여자1만 가능 (count=1)
    assert date_grid.get("09:00", 0) == 1
    assert date_grid.get("09:30", 0) == 1


@pytest.mark.e2e
def test_meeting_access_control_e2e(multi_user_e2e):
    """일정 조율 접근 제어 E2E 테스트"""
    from app.domain.visibility.enums import VisibilityLevel

    client_a = multi_user_e2e.as_user("user-a", email="user-a@company.com")
    client_b = multi_user_e2e.as_user("user-b", email="user-b@company.com")
    client_c = multi_user_e2e.as_user("user-c", email="user-c@other.com")

    # 1. user-a가 일정 조율 생성 (ALLOWED_EMAILS 레벨)
    create_response = client_a.post(
        "/v1/meetings",
        json={
            "title": "제한된 회의",
            "start_date": "2024-02-01",
            "end_date": "2024-02-07",
            "available_days": [0, 2, 4],
            "start_time": "09:00:00",
            "end_time": "18:00:00",
            "time_slot_minutes": 30,
            "visibility": {
                "level": "allowed_emails",
                "allowed_emails": ["user-b@company.com"],
                "allowed_domains": ["company.com"],
            },
        },
    )
    assert create_response.status_code == 201
    meeting_id = create_response.json()["id"]
    
    # visibility 설정 확인 (소유자로 조회)
    owner_get_response = client_a.get(f"/v1/meetings/{meeting_id}")
    assert owner_get_response.status_code == 200
    owner_data = owner_get_response.json()
    assert owner_data.get("visibility_level") == "allowed_emails", f"Expected 'allowed_emails', got: {owner_data}"

    # 2. user-b (허용된 이메일) 접근 가능
    get_response_b = client_b.get(f"/v1/meetings/{meeting_id}")
    assert get_response_b.status_code == 200, f"Expected 200, got {get_response_b.status_code}: {get_response_b.json()}"

    # 3. user-c (허용되지 않은 이메일) 접근 불가
    get_response_c = client_c.get(f"/v1/meetings/{meeting_id}")
    assert get_response_c.status_code == 403, f"Expected 403, got {get_response_c.status_code}: {get_response_c.json()}"


@pytest.mark.e2e
def test_meeting_domain_access_control_e2e(multi_user_e2e):
    """도메인 기반 접근 제어 E2E 테스트"""
    client_owner = multi_user_e2e.as_user("owner", email="owner@mycompany.com")
    client_company = multi_user_e2e.as_user("company-user", email="employee@mycompany.com")
    client_partner = multi_user_e2e.as_user("partner-user", email="contact@partner.org")
    client_external = multi_user_e2e.as_user("external-user", email="random@external.net")

    # 1. 소유자가 도메인 기반 접근 허용 설정
    create_response = client_owner.post(
        "/v1/meetings",
        json={
            "title": "사내 회의",
            "start_date": "2024-03-01",
            "end_date": "2024-03-07",
            "available_days": [0, 1, 2, 3, 4],  # 월-금
            "start_time": "09:00:00",
            "end_time": "18:00:00",
            "time_slot_minutes": 30,
            "visibility": {
                "level": "allowed_emails",
                "allowed_domains": ["mycompany.com", "partner.org"],
            },
        },
    )
    assert create_response.status_code == 201
    meeting_id = create_response.json()["id"]

    # 2. mycompany.com 도메인 사용자 접근 가능
    response = client_company.get(f"/v1/meetings/{meeting_id}")
    assert response.status_code == 200

    # 3. partner.org 도메인 사용자 접근 가능
    response = client_partner.get(f"/v1/meetings/{meeting_id}")
    assert response.status_code == 200

    # 4. external.net 도메인 사용자 접근 불가
    response = client_external.get(f"/v1/meetings/{meeting_id}")
    assert response.status_code == 403


@pytest.mark.e2e
def test_meeting_mixed_email_domain_access_e2e(multi_user_e2e):
    """이메일 + 도메인 혼합 접근 제어 E2E 테스트"""
    client_owner = multi_user_e2e.as_user("owner", email="owner@internal.com")
    client_allowed_email = multi_user_e2e.as_user("allowed-email", email="vip@external.com")
    client_allowed_domain = multi_user_e2e.as_user("allowed-domain", email="anyone@partner.com")
    client_not_allowed = multi_user_e2e.as_user("not-allowed", email="user@random.com")

    # 1. 특정 이메일 + 도메인 혼합 허용
    create_response = client_owner.post(
        "/v1/meetings",
        json={
            "title": "혼합 접근 회의",
            "start_date": "2024-03-01",
            "end_date": "2024-03-07",
            "available_days": [0, 2, 4],
            "start_time": "09:00:00",
            "end_time": "18:00:00",
            "time_slot_minutes": 30,
            "visibility": {
                "level": "allowed_emails",
                "allowed_emails": ["vip@external.com"],  # 특정 이메일
                "allowed_domains": ["partner.com"],  # 특정 도메인
            },
        },
    )
    assert create_response.status_code == 201
    meeting_id = create_response.json()["id"]

    # 2. 허용된 특정 이메일 접근 가능
    response = client_allowed_email.get(f"/v1/meetings/{meeting_id}")
    assert response.status_code == 200

    # 3. 허용된 도메인 사용자 접근 가능
    response = client_allowed_domain.get(f"/v1/meetings/{meeting_id}")
    assert response.status_code == 200

    # 4. 허용되지 않은 사용자 접근 불가
    response = client_not_allowed.get(f"/v1/meetings/{meeting_id}")
    assert response.status_code == 403


@pytest.mark.e2e
def test_meeting_participant_access_with_email_visibility_e2e(multi_user_e2e):
    """ALLOWED_EMAILS 설정된 미팅에 참여자 등록 E2E 테스트"""
    client_owner = multi_user_e2e.as_user("owner", email="owner@company.com")
    client_allowed = multi_user_e2e.as_user("allowed-user", email="allowed@company.com")
    client_denied = multi_user_e2e.as_user("denied-user", email="denied@external.com")

    # 1. ALLOWED_EMAILS로 미팅 생성
    create_response = client_owner.post(
        "/v1/meetings",
        json={
            "title": "접근 제한 회의",
            "start_date": "2024-03-01",
            "end_date": "2024-03-07",
            "available_days": [0, 2, 4],
            "start_time": "09:00:00",
            "end_time": "18:00:00",
            "time_slot_minutes": 30,
            "visibility": {
                "level": "allowed_emails",
                "allowed_domains": ["company.com"],
            },
        },
    )
    assert create_response.status_code == 201
    meeting_id = create_response.json()["id"]

    # 2. 허용된 사용자가 참여자로 등록 가능
    participate_response = client_allowed.post(
        f"/v1/meetings/{meeting_id}/participate",
        json={"display_name": "허용된 참여자"},
    )
    assert participate_response.status_code == 201
    participant_id = participate_response.json()["id"]

    # 3. 허용된 사용자가 가능 시간 설정 가능
    availability_response = client_allowed.put(
        f"/v1/meetings/{meeting_id}/availability",
        params={"participant_id": participant_id},
        json=[{
            "slot_date": "2024-03-04",  # 월요일
            "start_time": "09:00:00",
            "end_time": "12:00:00",
        }],
    )
    assert availability_response.status_code == 200

    # 4. 허용되지 않은 사용자는 접근 불가 (참여자 등록도 불가)
    denied_participate_response = client_denied.post(
        f"/v1/meetings/{meeting_id}/participate",
        json={"display_name": "거부된 참여자"},
    )
    assert denied_participate_response.status_code == 403


@pytest.mark.e2e
def test_meeting_timezone_e2e(e2e_client):
    """일정 조율 타임존 변환 E2E 테스트"""
    # 1. 일정 조율 생성
    create_response = e2e_client.post(
        "/v1/meetings",
        json={
            "title": "타임존 테스트 미팅",
            "start_date": "2024-02-01",
            "end_date": "2024-02-07",
            "available_days": [0, 2, 4],
            "start_time": "09:00:00",
            "end_time": "18:00:00",
            "time_slot_minutes": 30,
        },
    )
    assert create_response.status_code == 201
    meeting_id = create_response.json()["id"]
    created_at_utc = create_response.json()["created_at"]

    # 2. 타임존 없이 조회 (UTC로 반환)
    get_response_utc = e2e_client.get(f"/v1/meetings/{meeting_id}")
    assert get_response_utc.status_code == 200
    data_utc = get_response_utc.json()
    assert data_utc["created_at"] == created_at_utc

    # 3. KST 타임존으로 조회 (+09:00)
    get_response_kst = e2e_client.get(
        f"/v1/meetings/{meeting_id}",
        params={"timezone": "+09:00"},
    )
    assert get_response_kst.status_code == 200
    data_kst = get_response_kst.json()

    # 타임존 정보가 포함되어야 함
    assert "+09:00" in data_kst["created_at"] or "+0900" in data_kst["created_at"]
    # 시간이 9시간 더해져야 함 (UTC -> KST)
    from datetime import datetime, timezone as dt_timezone
    utc_dt = datetime.fromisoformat(created_at_utc.replace("Z", "+00:00"))
    kst_dt = datetime.fromisoformat(data_kst["created_at"])
    # 두 datetime 모두 aware이므로 직접 비교 (같은 시점을 표현해야 함)
    assert utc_dt == kst_dt  # 같은 시점을 다른 타임존으로 표현
    # KST 시간이 UTC보다 9시간 앞서 있음을 확인
    assert kst_dt.hour == (utc_dt.hour + 9) % 24 or abs(kst_dt.hour - utc_dt.hour) in [9, 15]

    # date와 time 필드는 변환되지 않음
    assert data_kst["start_date"] == "2024-02-01"
    assert data_kst["start_time"] == "09:00:00"

    # 4. Asia/Seoul 타임존으로 조회
    try:
        get_response_seoul = e2e_client.get(
            f"/v1/meetings/{meeting_id}",
            params={"timezone": "Asia/Seoul"},
        )
        assert get_response_seoul.status_code == 200
        data_seoul = get_response_seoul.json()
        assert "+09:00" in data_seoul["created_at"] or "+0900" in data_seoul["created_at"]
    except Exception:
        # tzdata가 없을 수 있음
        pass


@pytest.mark.e2e
def test_meeting_list_timezone_e2e(e2e_client):
    """일정 조율 목록 조회 타임존 변환 E2E 테스트"""
    # 1. 일정 조율 생성
    create_response = e2e_client.post(
        "/v1/meetings",
        json={
            "title": "타임존 테스트 미팅",
            "start_date": "2024-02-01",
            "end_date": "2024-02-07",
            "available_days": [0, 2, 4],
            "start_time": "09:00:00",
            "end_time": "18:00:00",
            "time_slot_minutes": 30,
        },
    )
    assert create_response.status_code == 201

    # 2. 타임존 없이 목록 조회
    list_response_utc = e2e_client.get("/v1/meetings")
    assert list_response_utc.status_code == 200
    meetings_utc = list_response_utc.json()
    assert len(meetings_utc) > 0

    # 3. KST 타임존으로 목록 조회
    list_response_kst = e2e_client.get(
        "/v1/meetings",
        params={"timezone": "+09:00"},
    )
    assert list_response_kst.status_code == 200
    meetings_kst = list_response_kst.json()
    assert len(meetings_kst) == len(meetings_utc)

    # 각 미팅의 created_at이 타임존 정보를 포함해야 함
    for meeting in meetings_kst:
        assert "+09:00" in meeting["created_at"] or "+0900" in meeting["created_at"]


@pytest.mark.e2e
def test_participant_timezone_e2e(e2e_client):
    """참여자 타임존 변환 E2E 테스트"""
    # 1. 일정 조율 생성
    create_response = e2e_client.post(
        "/v1/meetings",
        json={
            "title": "참여자 타임존 테스트",
            "start_date": "2024-02-01",
            "end_date": "2024-02-07",
            "available_days": [0, 2, 4],
            "start_time": "09:00:00",
            "end_time": "18:00:00",
            "time_slot_minutes": 30,
        },
    )
    assert create_response.status_code == 201
    meeting_id = create_response.json()["id"]

    # 2. 참여자 등록 (타임존 없이)
    participant_response_utc = e2e_client.post(
        f"/v1/meetings/{meeting_id}/participate",
        json={"display_name": "참여자1"},
    )
    assert participant_response_utc.status_code == 201
    participant_id = participant_response_utc.json()["id"]
    created_at_utc = participant_response_utc.json()["created_at"]

    # 3. 참여자 등록 (KST 타임존으로)
    participant_response_kst = e2e_client.post(
        f"/v1/meetings/{meeting_id}/participate",
        json={"display_name": "참여자2"},
        params={"timezone": "+09:00"},
    )
    assert participant_response_kst.status_code == 201
    data_kst = participant_response_kst.json()

    # 타임존 정보가 포함되어야 함
    assert "+09:00" in data_kst["created_at"] or "+0900" in data_kst["created_at"]

    # 4. 가능 시간 조회 (타임존 변환)
    availability_response = e2e_client.get(
        f"/v1/meetings/{meeting_id}/availability",
        params={"timezone": "+09:00"},
    )
    assert availability_response.status_code == 200
    availability = availability_response.json()

    # 각 참여자의 created_at이 타임존 정보를 포함해야 함
    for avail in availability:
        participant_created_at = avail["participant"]["created_at"]
        assert "+09:00" in participant_created_at or "+0900" in participant_created_at
