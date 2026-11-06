"""
커밋 후 큐(app/shared/uow.py enqueue_after_commit) 테스트

루트 커밋에서만 sink로 넘어가고, rollback·close에서는 버려지며,
SAVEPOINT(begin_nested)의 커밋·rollback은 큐를 건드리지 않는다.
"""
import pytest
from sqlalchemy import text
from sqlmodel import Session, create_engine

from app.shared import uow
from app.shared.uow import enqueue_after_commit, set_after_commit_sink


@pytest.fixture
def engine():
    engine = create_engine("sqlite://")
    yield engine
    engine.dispose()


def _write(session: Session) -> None:
    session.execute(text("SELECT 1"))


def test_root_commit_sends_items_in_order(engine, after_commit_items):
    with Session(engine) as session:
        _write(session)
        enqueue_after_commit(session, {"n": 1})
        enqueue_after_commit(session, {"n": 2})
        assert after_commit_items == []

        session.commit()

    assert after_commit_items == [{"n": 1}, {"n": 2}]


def test_items_sent_once(engine, after_commit_items):
    with Session(engine) as session:
        enqueue_after_commit(session, {"n": 1})
        session.commit()
        session.commit()

    assert after_commit_items == [{"n": 1}]


def test_root_rollback_drops_items(engine, after_commit_items):
    with Session(engine) as session:
        _write(session)
        enqueue_after_commit(session, {"n": 1})
        session.rollback()
        session.commit()

    assert after_commit_items == []


def test_close_without_commit_drops_items(engine, after_commit_items):
    session = Session(engine)
    _write(session)
    enqueue_after_commit(session, {"n": 1})
    session.close()

    session.commit()
    assert after_commit_items == []


def test_savepoint_commit_does_not_send(engine, after_commit_items):
    with Session(engine) as session:
        _write(session)
        enqueue_after_commit(session, {"n": 1})
        with session.begin_nested():
            _write(session)
        assert after_commit_items == []

        session.commit()

    assert after_commit_items == [{"n": 1}]


def test_savepoint_rollback_keeps_outer_items(engine, after_commit_items):
    with Session(engine) as session:
        _write(session)
        enqueue_after_commit(session, {"n": 1})
        savepoint = session.begin_nested()
        _write(session)
        savepoint.rollback()
        assert after_commit_items == []

        session.commit()

    assert after_commit_items == [{"n": 1}]


def test_sink_error_does_not_escape_commit(engine, monkeypatch):
    received = []
    logged = []
    monkeypatch.setattr(uow.logger, "exception", logged.append)

    def sink(item):
        if item["n"] == 1:
            raise RuntimeError("sink down")
        received.append(item)

    previous = set_after_commit_sink(sink)
    try:
        with Session(engine) as session:
            enqueue_after_commit(session, {"n": 1})
            enqueue_after_commit(session, {"n": 2})
            session.commit()
    finally:
        set_after_commit_sink(previous)

    assert received == [{"n": 2}]
    assert logged == ["after_commit_sink_failed"]


def test_default_sink_discards(engine):
    previous = set_after_commit_sink(None)
    try:
        with Session(engine) as session:
            enqueue_after_commit(session, {"n": 1})
            session.commit()
            assert "after_commit" not in session.info
    finally:
        set_after_commit_sink(previous)
