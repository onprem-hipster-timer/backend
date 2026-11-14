"""같은 사용자의 두 요청이 동시에 참여 등록할 때 참여자가 하나만 남는다 (PostgreSQL 전용)

SQLite는 쓰기를 다르게 직렬화해 unique 제약 대기를 재현할 수 없어 TEST_DATABASE_URL로만 돈다.
먼저 넣은 쪽이 커밋하기 전에 다른 쪽이 넣으려 하면 그쪽은 제약에서 기다렸다가 충돌을 받고,
SAVEPOINT만 되돌린 뒤 먼저 넣은 쪽의 참여자를 다시 읽어 표시 이름을 바꾼다.
"""
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, time as dtime

import pytest
from sqlmodel import Session, select

from app.domain.meeting.schema.dto import MeetingCreate, ParticipantCreate
from app.domain.meeting.service import MeetingService
from app.models.meeting import MeetingParticipant

_IS_POSTGRESQL = os.environ.get("TEST_DATABASE_URL", "").startswith("postgresql")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _IS_POSTGRESQL, reason="requires PostgreSQL via TEST_DATABASE_URL"),
]


def test_concurrent_participation_keeps_one(test_engine, test_user):
    with Session(test_engine) as session:
        meeting = MeetingService(session, test_user).create_meeting(MeetingCreate(
            title="동시 참여",
            start_date=date(2024, 2, 5),
            end_date=date(2024, 2, 9),
            available_days=[0, 1, 2, 3, 4],
            start_time=dtime(9),
            end_time=dtime(18),
        ))
        session.commit()
        meeting_id = meeting.id

    first_flushed = threading.Event()

    def first() -> tuple[str, bool]:
        with Session(test_engine) as session:
            participant, created = MeetingService(session, test_user).create_participant(
                meeting_id, ParticipantCreate(display_name="먼저"),
            )
            first_flushed.set()
            time.sleep(0.5)  # 다른 쪽이 제약에서 기다리는 동안 커밋을 늦춘다
            session.commit()
            return str(participant.id), created

    def second() -> tuple[str, bool]:
        assert first_flushed.wait(timeout=10)
        with Session(test_engine) as session:
            participant, created = MeetingService(session, test_user).create_participant(
                meeting_id, ParticipantCreate(display_name="나중"),
            )
            session.commit()
            return str(participant.id), created

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_result = pool.submit(first)
        second_result = pool.submit(second)
        results = (first_result.result(timeout=20), second_result.result(timeout=20))

    assert results[0][0] == results[1][0]
    assert [created for _, created in results] == [True, False]
    with Session(test_engine) as session:
        participants = session.exec(
            select(MeetingParticipant).where(MeetingParticipant.meeting_id == meeting_id)
        ).all()
    assert [p.display_name for p in participants] == ["나중"]
