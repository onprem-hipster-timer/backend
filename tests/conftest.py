import pytest
from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy.pool import StaticPool
from sqlalchemy import event
from app.models.schedule import Schedule


@pytest.fixture
def test_engine():
    """테스트용 DB 엔진"""
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    
    # SQLite에서 외래 키 제약 조건 활성화 (각 연결마다)
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    
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
def sample_timer(test_session, sample_schedule):
    """
    테스트용 타이머 데이터
    
    sample_schedule에 의존하여 일정이 먼저 생성되어야 함
    """
    from datetime import datetime, UTC
    from app.domain.timer.schema.dto import TimerCreate
    from app.domain.timer.service import TimerService
    
    timer_data = TimerCreate(
        schedule_id=sample_schedule.id,
        title="테스트 타이머",
        description="테스트 설명",
        allocated_duration=1800,  # 30분
    )
    
    service = TimerService(test_session)
    timer = service.create_timer(timer_data)
    test_session.flush()
    test_session.refresh(timer)
    return timer


@pytest.fixture
def e2e_client():
    """
    E2E 테스트용 FastAPI 클라이언트
    
    테스트용 메모리 SQLite 데이터베이스를 사용하고 테이블을 초기화합니다.
    
    Bug Fix: StaticPool 사용
    - SQLite 메모리 DB는 커넥션마다 별도 인스턴스를 가짐
    - StaticPool을 사용하여 모든 커넥션이 동일한 메모리 DB 인스턴스를 공유하도록 함
    """
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db.session import _session_manager
    
    # 테스트용 메모리 데이터베이스 엔진 생성
    # StaticPool을 사용하여 모든 커넥션이 동일한 메모리 DB를 공유
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    
    # SQLite에서 외래 키 제약 조건 활성화 (각 연결마다)
    @event.listens_for(test_engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    
    # SessionManager의 엔진을 테스트용으로 임시 교체 (init_db 전에 교체)
    original_engine = _session_manager.engine
    _session_manager.engine = test_engine
    
    # 테이블 생성 (교체된 엔진에 대해)
    SQLModel.metadata.create_all(test_engine)
    
    try:
        # TestClient 생성 (lifespan이 실행되지만 이미 테이블이 생성되어 있음)
        client = TestClient(app)
        yield client
    finally:
        # 원래 엔진으로 복원
        _session_manager.engine = original_engine
        # 테스트용 엔진 정리
        SQLModel.metadata.drop_all(test_engine)
        test_engine.dispose()

