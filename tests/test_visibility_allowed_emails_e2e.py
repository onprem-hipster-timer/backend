"""
Visibility ALLOWED_EMAILS E2E 테스트

허용 이메일·도메인은 대소문자를 구분하지 않고 비교하고, 앞뒤 공백을 지우고 소문자로 저장한다.
"""
import pytest

from app.core.auth import CurrentUser

SHARED_PARAMS = {"start_date": "2024-01-01T00:00:00Z", "end_date": "2024-01-01T23:59:59Z", "scope": "shared"}


def _share_schedule(owner, allowed_emails=None, allowed_domains=None) -> str:
    schedule_id = owner.post(
        "/v1/schedules",
        json={"title": "이메일 공개 일정", "start_time": "2024-01-01T10:00:00Z", "end_time": "2024-01-01T12:00:00Z"},
    ).json()["id"]
    body = {"level": "allowed_emails"}
    if allowed_emails is not None:
        body["allowed_emails"] = allowed_emails
    if allowed_domains is not None:
        body["allowed_domains"] = allowed_domains
    response = owner.put(f"/v1/visibility/schedule/{schedule_id}", json=body)
    assert response.status_code == 200
    return schedule_id


def _assert_can_view(viewer, schedule_id: str) -> None:
    assert viewer.get(f"/v1/schedules/{schedule_id}").status_code == 200
    shared = viewer.get("/v1/schedules", params=SHARED_PARAMS)
    assert shared.status_code == 200
    assert schedule_id in [s["id"] for s in shared.json()]


def _assert_cannot_view(viewer, schedule_id: str) -> None:
    assert viewer.get(f"/v1/schedules/{schedule_id}").status_code == 403
    shared = viewer.get("/v1/schedules", params=SHARED_PARAMS)
    assert shared.status_code == 200
    assert schedule_id not in [s["id"] for s in shared.json()]


@pytest.mark.e2e
def test_allowed_email_matches_viewer_email_in_lower_case(multi_user_e2e):
    owner = multi_user_e2e.as_user("owner")
    viewer = multi_user_e2e.as_user("viewer", email="alice@partner.com")
    schedule_id = _share_schedule(owner, allowed_emails=["Alice@Partner.COM"])

    _assert_can_view(viewer, schedule_id)


@pytest.mark.e2e
def test_allowed_email_matches_viewer_email_in_upper_case(multi_user_e2e):
    owner = multi_user_e2e.as_user("owner")
    viewer = multi_user_e2e.as_user("viewer", email="Alice@PARTNER.com")
    schedule_id = _share_schedule(owner, allowed_emails=["alice@partner.com"])

    _assert_can_view(viewer, schedule_id)


@pytest.mark.e2e
@pytest.mark.parametrize(
    ("allowed_domain", "viewer_email"),
    [
        ("Company.com", "user@company.com"),
        ("company.com", "User@COMPANY.COM"),
        ("COMPANY.COM", "user@Company.Com"),
    ],
)
def test_allowed_domain_matches_regardless_of_case(multi_user_e2e, allowed_domain, viewer_email):
    owner = multi_user_e2e.as_user("owner")
    viewer = multi_user_e2e.as_user("viewer", email=viewer_email)
    schedule_id = _share_schedule(owner, allowed_domains=[allowed_domain])

    _assert_can_view(viewer, schedule_id)


@pytest.mark.e2e
def test_allowed_domain_does_not_match_subdomain(multi_user_e2e):
    owner = multi_user_e2e.as_user("owner")
    viewer = multi_user_e2e.as_user("viewer", email="user@Sub.Example.com")
    schedule_id = _share_schedule(owner, allowed_domains=["Example.com"])

    _assert_cannot_view(viewer, schedule_id)


@pytest.mark.e2e
def test_other_email_is_still_denied(multi_user_e2e):
    owner = multi_user_e2e.as_user("owner")
    viewer = multi_user_e2e.as_user("viewer", email="bob@partner.com")
    schedule_id = _share_schedule(owner, allowed_emails=["Alice@Partner.com"])

    _assert_cannot_view(viewer, schedule_id)


@pytest.mark.e2e
def test_unverified_email_is_denied_regardless_of_case(multi_user_e2e):
    owner = multi_user_e2e.as_user("owner")
    multi_user_e2e._users["viewer"] = CurrentUser(
        sub="viewer", email="Alice@Partner.com", email_verified=False, name="Viewer",
    )
    viewer = multi_user_e2e.as_user("viewer")
    schedule_id = _share_schedule(owner, allowed_emails=["alice@partner.com"], allowed_domains=["Partner.com"])

    _assert_cannot_view(viewer, schedule_id)


@pytest.mark.e2e
def test_saved_list_is_trimmed_lower_cased_and_deduplicated(multi_user_e2e):
    owner = multi_user_e2e.as_user("owner")
    schedule_id = _share_schedule(
        owner,
        allowed_emails=[" Alice@Example.com ", "alice@example.com", "ALICE@EXAMPLE.COM", "Bob@Example.com"],
        allowed_domains=["Company.com", "company.com ", "Partner.org"],
    )

    data = owner.get(f"/v1/visibility/schedule/{schedule_id}").json()
    assert sorted(data["allowed_emails"]) == ["alice@example.com", "bob@example.com"]
    assert sorted(data["allowed_domains"]) == ["company.com", "partner.org"]
