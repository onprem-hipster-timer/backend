import pytest
from sqlmodel import SQLModel, create_engine, Session
from app.models.schedule import Schedule


@pytest.fixture
def test_engine():
    """테스트용 DB 엔진"""
    engine = create_engine("sqlite:///:memory:", echo=False)
    
    # 테스트용 테이블 생성
    SQLModel.metadata.create_all(engine)
    
    yield engine
    
    # 테스트 후 정리
    SQLModel.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def test_session(test_engine):
    """트랜잭션 기반 테스트 세션"""
    with Session(test_engine) as session:
        # 트랜잭션 시작
        transaction = session.begin()
        try:
            yield session
            # 각 테스트 후 자동 rollback
            transaction.rollback()
        except Exception:
            transaction.rollback()
            raise


@pytest.fixture
def sample_schedule(test_session):
    """테스트 데이터"""
    from datetime import datetime, UTC
    from app.domain.schedule.schema.schedule import ScheduleCreate
    
    schedule_data = ScheduleCreate(
        title="테스트 일정",
        description="테스트 설명",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
    )
    
    schedule = Schedule.model_validate(schedule_data)
    test_session.add(schedule)
    test_session.commit()
    test_session.refresh(schedule)
    return schedule

