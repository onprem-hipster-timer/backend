"""
get_db_committing 테스트

`Depends(get_db_committing, scope="function")`는 get_db_transactional과 같은 세션을 쓰고,
응답(http.response.start)을 보내기 전에 커밋해 커밋 후 큐를 처리한다.
"""
import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from app.db.session import _session_manager, get_db_committing, get_db_transactional
from app.shared.uow import enqueue_after_commit


@pytest.fixture(autouse=True)
def engine(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    monkeypatch.setattr(_session_manager, "engine", engine)
    yield engine
    engine.dispose()


def _sessions(session: Session = Depends(get_db_transactional)) -> Session:
    return session


def _client(items: list[dict], sent_at_response_start: list[list[dict]]) -> TestClient:
    """http.response.start가 나가는 순간 sink가 받은 항목을 기록하는 앱"""
    app = FastAPI()

    @app.post("/ok")
    def ok(
            other: Session = Depends(_sessions),
            session: Session = Depends(get_db_committing, scope="function"),
    ):
        assert session is other
        enqueue_after_commit(session, {"event": "ok"})
        return {"ok": True}

    @app.post("/fail")
    def fail(session: Session = Depends(get_db_committing, scope="function")):
        enqueue_after_commit(session, {"event": "fail"})
        raise HTTPException(status_code=400)

    async def recording(scope, receive, send):
        async def wrapped_send(message):
            if message["type"] == "http.response.start":
                sent_at_response_start.append(list(items))
            await send(message)

        await app(scope, receive, wrapped_send)

    return TestClient(recording)


def test_commits_before_response_start_with_shared_session(after_commit_items):
    sent_at_response_start: list[list[dict]] = []

    response = _client(after_commit_items, sent_at_response_start).post("/ok")

    assert response.status_code == 200
    assert sent_at_response_start == [[{"event": "ok"}]]
    assert after_commit_items == [{"event": "ok"}]


def test_error_skips_commit_and_drops_items(after_commit_items):
    response = _client(after_commit_items, []).post("/fail")

    assert response.status_code == 400
    assert after_commit_items == []
