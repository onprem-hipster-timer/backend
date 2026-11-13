"""두 요청이 동시에 기본 할 일 그룹을 만들 때 하나만 남는다 (PostgreSQL 전용)

SQLite는 쓰기를 다르게 직렬화해 부분 unique 인덱스 대기를 재현할 수 없어 TEST_DATABASE_URL로만 돈다.
먼저 넣은 쪽이 커밋하기 전에 다른 쪽이 넣으려 하면 그쪽은 인덱스에서 기다렸다가 충돌을 받고,
SAVEPOINT만 되돌린 뒤 먼저 넣은 쪽의 그룹을 다시 읽어야 한다.
"""
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlmodel import Session, select

from app.domain.todo_group.service import TodoGroupService
from app.models.todo_group import TodoGroup

_IS_POSTGRESQL = os.environ.get("TEST_DATABASE_URL", "").startswith("postgresql")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _IS_POSTGRESQL, reason="requires PostgreSQL via TEST_DATABASE_URL"),
]


def test_concurrent_default_creation_keeps_one(test_engine, test_user):
    first_flushed = threading.Event()

    def first() -> str:
        with Session(test_engine) as session:
            group = TodoGroupService(session, test_user).get_or_create_default()
            first_flushed.set()
            time.sleep(0.5)  # 다른 쪽이 인덱스에서 기다리는 동안 커밋을 늦춘다
            session.commit()
            return str(group.id)

    def second() -> str:
        assert first_flushed.wait(timeout=10)
        with Session(test_engine) as session:
            group = TodoGroupService(session, test_user).get_or_create_default()
            session.commit()
            return str(group.id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_id = pool.submit(first)
        second_id = pool.submit(second)
        ids = (first_id.result(timeout=20), second_id.result(timeout=20))

    assert ids[0] == ids[1]
    with Session(test_engine) as session:
        defaults = session.exec(
            select(TodoGroup).where(TodoGroup.owner_id == test_user.sub).where(TodoGroup.is_default)
        ).all()
    assert len(defaults) == 1
