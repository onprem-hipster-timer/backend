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
    """
    테스트 데이터
    
    Bug Fix: commit() 제거, flush() 사용
    - test_session fixture는 rollback 기반 격리를 제공
    - commit()을 호출하면 트랜잭션이 커밋되어 rollback이 작동하지 않음
    - flush()를 사용하여 ID를 얻고, 트랜잭션은 test_session이 rollback 처리
    """
    from datetime import datetime, UTC
    from app.domain.schedule.schema.dto import ScheduleCreate
    
    schedule_data = ScheduleCreate(
        title="테스트 일정",
        description="테스트 설명",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
    )
    
    schedule = Schedule.model_validate(schedule_data)
    test_session.add(schedule)
    # Bug Fix: commit() 대신 flush() 사용 (트랜잭션 격리 유지)
    test_session.flush()  # ID를 얻기 위해 flush
    test_session.refresh(schedule)
    return schedule


@pytest.fixture
def e2e_client():
    """
    E2E 테스트용 FastAPI 클라이언트
    
    테스트용 메모리 SQLite 데이터베이스를 사용하고 테이블을 초기화합니다.
    """
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db.session import _session_manager
    
    # 테스트용 메모리 데이터베이스 엔진 생성
    test_engine = create_engine("sqlite:///:memory:", echo=False)
    
    # 테이블 생성
    SQLModel.metadata.create_all(test_engine)
    
    # SessionManager의 엔진을 테스트용으로 임시 교체
    original_engine = _session_manager.engine
    _session_manager.engine = test_engine
    
    try:
        # TestClient 생성 (lifespan이 실행됨)
        client = TestClient(app)
        yield client
    finally:
        # 원래 엔진으로 복원
        _session_manager.engine = original_engine
        # 테스트용 엔진 정리
        SQLModel.metadata.drop_all(test_engine)
        test_engine.dispose()

