"""PostgreSQL에서 같은 (sub, version)의 동의 기록이 겹칠 때 (app/domain/consent/service.py record_consent)

회원·게스트 경로가 앞에서 잡는 프로필·게스트 행 잠금 없이 서비스를 바로 부른다. 한쪽 트랜잭션을 커밋 전에 멈춰 두고
다른 쪽을 시작한다. 뒤의 요청은 앞 요청의 행 잠금을 기다린 뒤 끝나고, 처음 동의한 행(consented_at)은 앞 요청의
것이며, 보낸 사용성 분석 동의(analytics)는 뒤 요청의 값이 남는다. 같은 값이면 앞 요청의 시각을 둔다.
SQLite는 행을 잠그지 않으므로 TEST_DATABASE_URL이 PostgreSQL일 때만 돈다.
"""
import asyncio
import os
import threading
from datetime import datetime

import pytest
from sqlalchemy import create_engine, insert, text
from sqlmodel import Session, select

import app.core.config as app_config
from app.domain.consent import service
from app.domain.consent.schema.dto import ConsentCreate
from app.models.consent import Consent

_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _DATABASE_URL.startswith("postgresql"), reason="requires PostgreSQL via TEST_DATABASE_URL for row locks"
    ),
]

# 멈춘 트랜잭션 뒤에서 다른 쪽이 끝나지 않는지 지켜보는 시간과, 어떤 기다림이든 넘지 않는 시간
HOLD_SECONDS = 1
BOUND_SECONDS = 30
EARLIER = datetime(2026, 1, 1)


@pytest.fixture
def released():
    """멈춘 트랜잭션을 놓는 신호. 테스트가 중간에 실패해도 끝에서 놓는다"""
    event = threading.Event()
    yield event
    event.set()


def _consent(analytics: bool | None) -> ConsentCreate:
    return ConsentCreate(
        version=app_config.settings.CONSENT_VERSION, age_over_14=True, terms=True, privacy=True, analytics=analytics
    )


def _record(engine, analytics: bool | None, recorded=None, released=None) -> tuple:
    """동의를 기록하고 (recorded가 있으면 알린 뒤 released까지 멈췄다가) 커밋한다. 기록한 행의 값을 돌려준다"""
    with Session(engine) as session:
        row = service.record_consent(session, "a", _consent(analytics))
        values = (row.analytics, row.analytics_updated_at, row.consented_at)
        if recorded is not None:
            recorded.set()
            released.wait(BOUND_SECONDS)
        session.commit()
        return values


def _stored(engine) -> list[tuple]:
    with Session(engine) as session:
        return [(c.analytics, c.analytics_updated_at, c.consented_at) for c in session.exec(select(Consent)).all()]


def _lock_waiters() -> int:
    """이 DB에서 행 잠금을 기다리는 연결 수"""
    probe = create_engine(_DATABASE_URL)
    try:
        with probe.connect() as conn:
            return conn.execute(text(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname = current_database() AND wait_event_type = 'Lock'"
            )).scalar()
    finally:
        probe.dispose()


async def _first_then_second(engine, released, first: bool | None, second: bool | None) -> tuple[tuple, tuple]:
    recorded = threading.Event()
    earlier = asyncio.create_task(asyncio.to_thread(_record, engine, first, recorded, released))
    assert await asyncio.to_thread(recorded.wait, BOUND_SECONDS)

    later = asyncio.create_task(asyncio.to_thread(_record, engine, second))
    done, _ = await asyncio.wait({later}, timeout=HOLD_SECONDS)
    assert not done
    assert _lock_waiters() == 1

    released.set()
    return await asyncio.wait_for(asyncio.gather(earlier, later), BOUND_SECONDS)


@pytest.mark.parametrize("first, second", [(True, False), (False, True), (None, True), (True, None)])
@pytest.mark.asyncio
async def test_overlapping_first_consents_keep_first_row_and_last_analytics(test_engine, released, first, second):
    earlier, _ = await _first_then_second(test_engine, released, first, second)

    [(analytics, chosen_at, consented_at)] = _stored(test_engine)
    assert consented_at == earlier[2]
    assert analytics is (first if second is None else second)
    assert (chosen_at == earlier[1]) is (second is None)


@pytest.mark.parametrize("first, second", [(True, False), (False, True), (True, True), (False, False)])
@pytest.mark.asyncio
async def test_overlapping_changes_keep_last_value_and_its_time(test_engine, released, first, second):
    with Session(test_engine) as session:
        session.execute(insert(Consent).values(sub="a", version=app_config.settings.CONSENT_VERSION,
                                               consented_at=EARLIER))
        session.commit()

    earlier, later = await _first_then_second(test_engine, released, first, second)

    assert _stored(test_engine) == [(second, later[1], EARLIER)]
    assert (later[1] == earlier[1]) is (first == second)
