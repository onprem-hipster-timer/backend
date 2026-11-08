"""
타이머 할당 시간 상한 테스트

- elapsed_time은 allocated_duration을 넘지 않는다 (stop, pause, Todo DONE 전파)

시각은 started_at을 DB에 직접 과거로 기록해 흘려보낸다.
"""
from datetime import datetime, timedelta, UTC
from uuid import UUID

import pytest
from sqlalchemy import update
from sqlmodel import Session

from app.db.session import _session_manager
from app.domain.timer.model import TimerSession

ALLOCATED = 60


def _create(client, **body) -> dict:
    response = client.post("/v1/timers", json={"title": "만료 타이머", "allocated_duration": ALLOCATED, **body})
    assert response.status_code == 201, response.text
    return response.json()


def _backdate(timer_id: str, seconds: int) -> datetime:
    """started_at을 seconds초 전으로 DB에 직접 기록하고 그 값을 반환"""
    started_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=seconds)
    with Session(_session_manager.engine) as session:
        session.execute(
            update(TimerSession).where(TimerSession.id == UUID(timer_id)).values(started_at=started_at)
        )
        session.commit()
    return started_at


@pytest.mark.e2e
@pytest.mark.parametrize("action", ["pause", "stop"])
def test_elapsed_is_capped_at_allocated(e2e_client, action):
    timer_id = _create(e2e_client)["id"]
    _backdate(timer_id, ALLOCATED * 10)

    method = e2e_client.post if action == "stop" else e2e_client.patch
    response = method(f"/v1/timers/{timer_id}/{action}")

    assert response.status_code == 200
    assert response.json()["elapsed_time"] == ALLOCATED


@pytest.mark.e2e
def test_todo_done_long_after_expiry_completes_with_allocated(e2e_client):
    group = e2e_client.post("/v1/tags/groups", json={"name": "그룹", "color": "#FF5733"}).json()
    todo = e2e_client.post("/v1/todos", json={"title": "할 일", "tag_group_id": group["id"]}).json()
    timer_id = _create(e2e_client, todo_id=todo["id"])["id"]
    _backdate(timer_id, ALLOCATED * 10)

    response = e2e_client.patch(f"/v1/todos/{todo['id']}", json={"status": "DONE"})

    assert response.status_code == 200, response.text
    timer = e2e_client.get(f"/v1/timers/{timer_id}").json()
    assert timer["status"] == "COMPLETED"
    assert timer["elapsed_time"] == ALLOCATED
