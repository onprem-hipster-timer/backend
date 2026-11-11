"""
Visibility - Meeting 도메인 E2E 테스트

미팅(일정 조율) 접근권한 설정 및 접근 제어 통합 테스트
"""
import pytest


def _make_meeting(client, title="테스트 미팅"):
    return client.post(
        "/v1/meetings",
        json={
            "title": title,
            "start_date": "2024-02-01",
            "end_date": "2024-02-07",
            "available_days": [0, 2, 4],
            "start_time": "09:00:00",
            "end_time": "18:00:00",
            "time_slot_minutes": 30,
        },
    ).json()["id"]


@pytest.mark.e2e
def test_set_and_get_visibility_meeting(e2e_client):
    """미팅 접근권한 설정 및 조회 E2E 테스트"""
    meeting_id = _make_meeting(e2e_client, "접근권한 테스트 미팅")

    vis_response = e2e_client.put(
        f"/v1/visibility/meeting/{meeting_id}",
        json={
            "level": "allowed_emails",
            "allowed_emails": ["user@company.com"],
            "allowed_domains": ["company.com"],
        },
    )
    assert vis_response.status_code == 200
    vis_data = vis_response.json()
    assert vis_data["level"] == "allowed_emails"
    assert vis_data["resource_type"] == "meeting"
    assert "user@company.com" in vis_data["allowed_emails"]
    assert "company.com" in vis_data["allowed_domains"]

    get_response = e2e_client.get(f"/v1/visibility/meeting/{meeting_id}")
    assert get_response.status_code == 200
    assert get_response.json()["level"] == "allowed_emails"

    # 미팅 단건 조회 시 visibility_level 반영 확인
    meeting_data = e2e_client.get(f"/v1/meetings/{meeting_id}").json()
    assert meeting_data["visibility_level"] == "allowed_emails"


@pytest.mark.e2e
def test_meeting_access_control_e2e(multi_user_e2e):
    """일정 조율 이메일 기반 접근 제어 E2E 테스트"""
    client_a = multi_user_e2e.as_user("user-a", email="user-a@company.com")
    client_b = multi_user_e2e.as_user("user-b", email="user-b@company.com")
    client_c = multi_user_e2e.as_user("user-c", email="user-c@other.com")

    meeting_id = _make_meeting(client_a, "제한된 회의")

    vis_response = client_a.put(
        f"/v1/visibility/meeting/{meeting_id}",
        json={
            "level": "allowed_emails",
            "allowed_emails": ["user-b@company.com"],
            "allowed_domains": ["company.com"],
        },
    )
    assert vis_response.status_code == 200
    assert client_a.get(f"/v1/meetings/{meeting_id}").json().get("visibility_level") == "allowed_emails"

    assert client_b.get(f"/v1/meetings/{meeting_id}").status_code == 200
    assert client_c.get(f"/v1/meetings/{meeting_id}").status_code == 403


@pytest.mark.e2e
def test_meeting_domain_access_control_e2e(multi_user_e2e):
    """도메인 기반 접근 제어 E2E 테스트"""
    client_owner = multi_user_e2e.as_user("owner", email="owner@mycompany.com")
    client_company = multi_user_e2e.as_user("company-user", email="employee@mycompany.com")
    client_partner = multi_user_e2e.as_user("partner-user", email="contact@partner.org")
    client_external = multi_user_e2e.as_user("external-user", email="random@external.net")

    meeting_id = _make_meeting(client_owner, "사내 회의")

    vis_response = client_owner.put(
        f"/v1/visibility/meeting/{meeting_id}",
        json={"level": "allowed_emails", "allowed_domains": ["mycompany.com", "partner.org"]},
    )
    assert vis_response.status_code == 200

    assert client_company.get(f"/v1/meetings/{meeting_id}").status_code == 200
    assert client_partner.get(f"/v1/meetings/{meeting_id}").status_code == 200
    assert client_external.get(f"/v1/meetings/{meeting_id}").status_code == 403


@pytest.mark.e2e
def test_meeting_mixed_email_domain_access_e2e(multi_user_e2e):
    """이메일 + 도메인 혼합 접근 제어 E2E 테스트"""
    client_owner = multi_user_e2e.as_user("owner", email="owner@internal.com")
    client_allowed_email = multi_user_e2e.as_user("allowed-email", email="vip@external.com")
    client_allowed_domain = multi_user_e2e.as_user("allowed-domain", email="anyone@partner.com")
    client_not_allowed = multi_user_e2e.as_user("not-allowed", email="user@random.com")

    meeting_id = _make_meeting(client_owner, "혼합 접근 회의")

    vis_response = client_owner.put(
        f"/v1/visibility/meeting/{meeting_id}",
        json={
            "level": "allowed_emails",
            "allowed_emails": ["vip@external.com"],
            "allowed_domains": ["partner.com"],
        },
    )
    assert vis_response.status_code == 200

    assert client_allowed_email.get(f"/v1/meetings/{meeting_id}").status_code == 200
    assert client_allowed_domain.get(f"/v1/meetings/{meeting_id}").status_code == 200
    assert client_not_allowed.get(f"/v1/meetings/{meeting_id}").status_code == 403


@pytest.mark.e2e
def test_meeting_participant_access_with_email_visibility_e2e(multi_user_e2e):
    """ALLOWED_EMAILS 설정된 미팅에 참여자 등록 E2E 테스트"""
    client_owner = multi_user_e2e.as_user("owner", email="owner@company.com")
    client_allowed = multi_user_e2e.as_user("allowed-user", email="allowed@company.com")
    client_denied = multi_user_e2e.as_user("denied-user", email="denied@external.com")

    meeting_id = _make_meeting(client_owner, "접근 제한 회의")

    vis_response = client_owner.put(
        f"/v1/visibility/meeting/{meeting_id}",
        json={"level": "allowed_emails", "allowed_domains": ["company.com"]},
    )
    assert vis_response.status_code == 200

    participate_response = client_allowed.post(
        f"/v1/meetings/{meeting_id}/participate",
        json={"display_name": "허용된 참여자"},
    )
    assert participate_response.status_code == 201
    participant_id = participate_response.json()["id"]

    availability_response = client_allowed.put(
        f"/v1/meetings/{meeting_id}/availability",
        params={"participant_id": participant_id},
        json=[{"slot_date": "2024-02-05", "start_time": "09:00:00", "end_time": "12:00:00"}],
    )
    assert availability_response.status_code == 200

    denied_response = client_denied.post(
        f"/v1/meetings/{meeting_id}/participate",
        json={"display_name": "거부된 참여자"},
    )
    assert denied_response.status_code == 403


@pytest.mark.e2e
def test_owner_deletes_meeting_with_participants_e2e(multi_user_e2e):
    """참여자와 가능 시간이 있는 미팅도 삭제되고, 참여 기록과 가능 시간이 함께 사라진다"""
    from sqlmodel import Session, select

    from app.db.session import _session_manager
    from app.models.meeting import MeetingParticipant, MeetingTimeSlot

    client_owner = multi_user_e2e.as_user("owner", email="owner@company.com")
    client_member = multi_user_e2e.as_user("member", email="member@company.com")

    meeting_id = _make_meeting(client_owner, "참여자 있는 회의")
    client_owner.put(
        f"/v1/visibility/meeting/{meeting_id}",
        json={"level": "allowed_emails", "allowed_domains": ["company.com"]},
    )
    for client, name in ((client_owner, "주최자"), (client_member, "참여자")):
        participant_id = client.post(
            f"/v1/meetings/{meeting_id}/participate", json={"display_name": name}
        ).json()["id"]
        r = client.put(
            f"/v1/meetings/{meeting_id}/availability",
            params={"participant_id": participant_id},
            json=[{"slot_date": "2024-02-05", "start_time": "09:00:00", "end_time": "12:00:00"}],
        )
        assert r.status_code == 200

    response = client_owner.delete(f"/v1/meetings/{meeting_id}")

    assert response.status_code == 200, response.text
    assert client_member.get(f"/v1/meetings/{meeting_id}").status_code == 404
    with Session(_session_manager.engine) as session:
        assert session.exec(select(MeetingParticipant)).all() == []
        assert session.exec(select(MeetingTimeSlot)).all() == []
