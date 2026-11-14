"""
타이머 목록 started_at 범위 경계 E2E 테스트

start_date/end_date는 [start_date, end_date) 범위이고 started_at이 그 안에 있는 타이머를 돌려준다.
"""
from datetime import datetime

import pytest
from sqlmodel import Session

from app.core.constants import TimerStatus
from app.db.session import _session_manager
from app.models.timer import TimerSession

OWNER = "user-a"
VIEWER = "user-c"
STARTED_AT = datetime(2024, 3, 10, 9, 0)


def _insert_timer(owner_id: str, title: str) -> str:
    with Session(_session_manager.engine) as session:
        timer = TimerSession(
            owner_id=owner_id,
            title=title,
            allocated_duration=1500,
            elapsed_time=1500,
            status=TimerStatus.COMPLETED,
            started_at=STARTED_AT,
            ended_at=STARTED_AT,
        )
        session.add(timer)
        session.commit()
        return str(timer.id)


def _titles(client, start: str, end: str, scope: str = "mine") -> list[str]:
    response = client.get("/v1/timers", params={"start_date": start, "end_date": end, "scope": scope})
    assert response.status_code == 200, response.text
    return [t["title"] for t in response.json()]


@pytest.mark.e2e
@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        ("2024-03-10T09:00:00Z", "2024-03-10T10:00:00Z", ["timer"]),  # 시작 = started_at
        ("2024-03-10T08:00:00Z", "2024-03-10T09:00:00Z", []),  # 끝 = started_at
        ("2024-03-10T08:00:00Z", "2024-03-10T09:00:01Z", ["timer"]),
        ("2024-03-10T00:00:00+09:00", "2024-03-11T00:00:00+09:00", ["timer"]),
        ("2024-03-10T18:00:00+09:00", "2024-03-11T00:00:00+09:00", ["timer"]),  # 시작 = started_at (KST)
        ("2024-03-09T00:00:00+09:00", "2024-03-10T18:00:00+09:00", []),  # 끝 = started_at (KST)
    ],
)
def test_my_timers_range_is_half_open(e2e_client, start, end, expected):
    _insert_timer("test-user-id", "timer")

    assert _titles(e2e_client, start, end) == expected


@pytest.mark.e2e
@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        ("2024-03-10T09:00:00Z", "2024-03-10T10:00:00Z", ["shared"]),
        ("2024-03-10T08:00:00Z", "2024-03-10T09:00:00Z", []),
        ("2024-03-10T18:00:00+09:00", "2024-03-11T00:00:00+09:00", ["shared"]),
        ("2024-03-09T00:00:00+09:00", "2024-03-10T18:00:00+09:00", []),
    ],
)
def test_shared_timers_range_is_half_open(multi_user_e2e, start, end, expected):
    owner = multi_user_e2e.as_user(OWNER)
    viewer = multi_user_e2e.as_user(VIEWER)
    timer_id = _insert_timer(OWNER, "shared")
    response = owner.put(f"/v1/visibility/timer/{timer_id}", json={"level": "public"})
    assert response.status_code == 200, response.text

    assert _titles(viewer, start, end, scope="shared") == expected
