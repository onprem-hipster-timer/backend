import os

# 테스트 환경 기본 설정 - 다른 모듈 임포트 전에 설정 필요!
os.environ["OIDC_ENABLED"] = "false"
os.environ["RATE_LIMIT_ENABLED"] = "false"  # 기본 비활성화, 레이트 리밋 테스트에서만 활성화

import pytest
import pytest_asyncio
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine, Session

from app.core.auth import CurrentUser


# ============ DB 타입 헬퍼 함수 ============

def _get_test_database_url() -> str | None:
    """TEST_DATABASE_URL 환경변수 반환 (없으면 None)"""
    return os.environ.get("TEST_DATABASE_URL")


def _is_postgresql(url: str) -> bool:
    """PostgreSQL URL인지 확인"""
    return url.startswith("postgresql")


def _get_async_url(url: str) -> str:
    """동기 URL을 비동기 URL로 변환"""
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


@pytest.fixture
def test_user() -> CurrentUser:
    """테스트용 사용자 (OIDC 비활성화 시 반환되는 mock 사용자와 동일)"""
    return CurrentUser(
        sub="test-user-id",
        email="test@example.com",
        name="Test User",
    )


@pytest.fixture
def test_engine():
    """
    테스트용 DB 엔진
    
    TEST_DATABASE_URL 환경변수가 설정되면 해당 DB 사용,
    없으면 SQLite 메모리 DB 사용
    """
    test_db_url = _get_test_database_url()
    
    if test_db_url and _is_postgresql(test_db_url):
        # PostgreSQL 사용
        engine = create_engine(
            test_db_url,
            echo=False,
            pool_pre_ping=True,
        )
        
        # 테스트용 테이블 생성
        SQLModel.metadata.create_all(engine)
        
        yield engine
        
        # 테스트 후 정리 (테이블 삭제)
        SQLModel.metadata.drop_all(engine)
        engine.dispose()
    else:
        # SQLite 메모리 DB 사용 (기본값)
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


@pytest_asyncio.fixture
async def test_async_engine():
    """
    테스트용 비동기 DB 엔진
    
    TEST_DATABASE_URL 환경변수가 설정되면 해당 DB 사용,
    없으면 SQLite 메모리 DB 사용
    """
    test_db_url = _get_test_database_url()
    
    if test_db_url and _is_postgresql(test_db_url):
        # PostgreSQL 비동기 엔진 생성
        async_url = _get_async_url(test_db_url)
        engine = create_async_engine(
            async_url,
            echo=False,
            pool_pre_ping=True,
        )
        
        # 테스트용 테이블 생성
        from app.domain.holiday.model import HolidayModel, HolidayHashModel  # noqa: F401

        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

        yield engine

        # 테스트 후 정리
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)
        await engine.dispose()
    else:
        # SQLite 비동기 엔진 생성 (기본값)
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            echo=False,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        # SQLite에서 외래 키 제약 조건 활성화
        @event.listens_for(engine.sync_engine, "connect")
        def set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        # 테스트용 테이블 생성
        from app.domain.holiday.model import HolidayModel, HolidayHashModel  # noqa: F401

        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

        yield engine

        # 테스트 후 정리
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)
        await engine.dispose()


@pytest_asyncio.fixture
async def test_async_session(test_async_engine):
    """트랜잭션 기반 비동기 테스트 세션"""
    async_session_maker = async_sessionmaker(
        test_async_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_maker() as session:
        # 트랜잭션 시작
        transaction = await session.begin()
        try:
            yield session
            # 각 테스트 후 자동 rollback
            await transaction.rollback()
        except Exception:
            await transaction.rollback()
            raise


@pytest.fixture
def sample_schedule(test_session, test_user):
    """
    테스트 데이터
    
    Bug Fix: commit() 제거, flush() 사용
    - test_session fixture는 rollback 기반 격리를 제공
    - commit()을 호출하면 트랜잭션이 커밋되어 rollback이 작동하지 않음
    - flush()를 사용하여 ID를 얻고, 트랜잭션은 test_session이 rollback 처리
    """
    from datetime import datetime, UTC
    from app.domain.schedule.schema.dto import ScheduleCreate
    from app.domain.schedule.service import ScheduleService

    schedule_data = ScheduleCreate(
        title="테스트 일정",
        description="테스트 설명",
        start_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
    )

    # ScheduleService를 통해 owner_id와 함께 일정 생성
    service = ScheduleService(test_session, test_user)
    schedule = service.create_schedule(schedule_data)
    # Bug Fix: commit() 대신 flush() 사용 (트랜잭션 격리 유지)
    test_session.flush()  # ID를 얻기 위해 flush
    test_session.refresh(schedule)
    return schedule


@pytest.fixture
def sample_timer(test_session, sample_schedule, test_user):
    """
    테스트용 타이머 데이터
    
    sample_schedule에 의존하여 일정이 먼저 생성되어야 함
    """
    from app.domain.timer.schema.dto import TimerCreate
    from app.domain.timer.service import TimerService

    timer_data = TimerCreate(
        schedule_id=sample_schedule.id,
        title="테스트 타이머",
        description="테스트 설명",
        allocated_duration=1800,  # 30분
    )

    service = TimerService(test_session, test_user)
    timer = service.create_timer(timer_data)
    test_session.flush()
    test_session.refresh(timer)
    return timer


@pytest.fixture
def sample_tag_group(test_session, test_user):
    """
    테스트용 태그 그룹 데이터
    """
    from app.domain.tag.schema.dto import TagGroupCreate
    from app.domain.tag.service import TagService

    group_data = TagGroupCreate(
        name="테스트 그룹",
        color="#FF5733",
        description="테스트 태그 그룹",
        is_todo_group=True,
    )

    service = TagService(test_session, test_user)
    group = service.create_tag_group(group_data)
    test_session.flush()
    test_session.refresh(group)
    return group


@pytest.fixture
def sample_todo(test_session, sample_tag_group, test_user):
    """
    테스트용 Todo 데이터
    
    sample_tag_group에 의존하여 태그 그룹이 먼저 생성되어야 함
    """
    from app.domain.todo.schema.dto import TodoCreate
    from app.domain.todo.service import TodoService

    todo_data = TodoCreate(
        title="테스트 Todo",
        description="테스트 설명",
        tag_group_id=sample_tag_group.id,
    )

    service = TodoService(test_session, test_user)
    todo = service.create_todo(todo_data)
    test_session.flush()
    test_session.refresh(todo)
    return todo


@pytest.fixture
def todo_with_schedule(test_session, sample_tag_group, test_user):
    """
    deadline이 있는 Todo (연관된 Schedule이 자동 생성됨)
    
    Todo → Schedule 자동 연결 테스트용
    """
    from datetime import datetime, UTC, timedelta
    from app.domain.todo.schema.dto import TodoCreate
    from app.domain.todo.service import TodoService

    # deadline이 있는 Todo 생성 → Schedule 자동 생성
    deadline = datetime.now(UTC) + timedelta(days=7)
    todo_data = TodoCreate(
        title="마감이 있는 Todo",
        description="연관 Schedule이 있는 Todo",
        tag_group_id=sample_tag_group.id,
        deadline=deadline,
    )

    service = TodoService(test_session, test_user)
    todo = service.create_todo(todo_data)
    test_session.flush()
    test_session.refresh(todo)
    return todo


@pytest.fixture
def schedule_with_source_todo(test_session, todo_with_schedule, test_user):
    """
    source_todo_id가 있는 Schedule (Todo에서 자동 생성된 Schedule)
    
    Schedule → Todo 자동 연결 테스트용
    """
    # todo_with_schedule의 연관된 Schedule 반환
    test_session.refresh(todo_with_schedule)
    assert len(todo_with_schedule.schedules) > 0, "Todo에 연관된 Schedule이 없습니다"
    return todo_with_schedule.schedules[0]


@pytest.fixture
def e2e_client():
    """
    E2E 테스트용 FastAPI 클라이언트
    
    TEST_DATABASE_URL 환경변수가 설정되면 해당 DB 사용,
    없으면 SQLite 메모리 DB 사용
    
    Bug Fix: StaticPool 사용 (SQLite 전용)
    - SQLite 메모리 DB는 커넥션마다 별도 인스턴스를 가짐
    - StaticPool을 사용하여 모든 커넥션이 동일한 메모리 DB 인스턴스를 공유하도록 함
    
    Bug Fix: settings 재로드 + 스토리지 초기화
    - 레이트 리밋 테스트 후 settings가 변경될 수 있으므로 재로드하여 비활성화 보장
    - 레이트 리밋 스토리지도 초기화하여 이전 테스트의 카운트가 영향을 주지 않도록 함
    """
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db.session import _session_manager

    # 환경변수를 명시적으로 설정하고 settings 재로드
    # (레이트 리밋 테스트에서 환경변수가 변경될 수 있음)
    os.environ["RATE_LIMIT_ENABLED"] = "false"
    os.environ["OIDC_ENABLED"] = "false"

    from app.core.config import Settings
    import app.core.config as config_module
    config_module.settings = Settings()

    # 레이트 리밋 스토리지 초기화 (이전 테스트의 카운트 제거)
    from app.ratelimit.storage.memory import reset_storage
    reset_storage()

    test_db_url = _get_test_database_url()
    
    if test_db_url and _is_postgresql(test_db_url):
        # PostgreSQL 사용
        test_engine = create_engine(
            test_db_url,
            echo=False,
            pool_pre_ping=True,
        )
    else:
        # SQLite 메모리 DB 사용 (기본값)
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
