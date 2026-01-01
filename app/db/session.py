import logging
from contextlib import contextmanager
from typing import Generator
from urllib.parse import urlparse

from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlmodel import SQLModel, create_engine, Session

from app.core.config import settings

logger = logging.getLogger(__name__)


class SessionManager:
    """세션 관리자 - Context Manager 패턴"""

    def __init__(self):
        self.engine = None
        self._init_engine()

    def _init_engine(self):
        """엔진 초기화"""
        connect_args = {}

        # SQLite인 경우 외래 키 제약 조건 활성화
        if settings.DATABASE_URL.startswith("sqlite"):
            connect_args = {"check_same_thread": False}

        self.engine = create_engine(
            settings.DATABASE_URL,
            echo=settings.DEBUG,
            pool_size=settings.POOL_SIZE,
            max_overflow=settings.MAX_OVERFLOW,
            connect_args=connect_args,
        )

        # SQLite인 경우 외래 키 제약 조건 활성화 (각 연결마다)
        if settings.DATABASE_URL.startswith("sqlite"):
            @event.listens_for(self.engine, "connect")
            def set_sqlite_pragma(dbapi_conn, connection_record):
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

    @contextmanager
    def get_session(self):
        """
        Context Manager를 통한 세션 관리
        - with 블록 종료 시 자동 close
        """
        with Session(self.engine) as session:
            yield session

    def init_db(self):
        """데이터베이스 초기화"""
        SQLModel.metadata.create_all(self.engine)


# 전역 인스턴스
_session_manager = SessionManager()


def init_db():
    """데이터베이스 초기화 (main.py에서 호출)"""
    _session_manager.init_db()


def get_db() -> Generator[Session, None, None]:
    """
    읽기 전용 세션 (commit 없음)
    - GET 요청 등 읽기 작업에 사용
    - FastAPI가 자동으로 세션 close 처리
    """
    with _session_manager.get_session() as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            if session.new or session.dirty or session.deleted:
                logger.warning(
                    "Read-only session rolled back with pending changes. "
                    "new=%d dirty=%d deleted=%d",
                    len(session.new),
                    len(session.dirty),
                    len(session.deleted),
                )
            session.rollback()


def get_db_transactional() -> Generator[Session, None, None]:
    """
    트랜잭션 자동 관리 세션
    - POST/PUT/DELETE 등 쓰기 작업에 사용
    - 함수 종료 성공: commit 자동
    - 예외 발생: rollback 자동
    """
    with _session_manager.get_session() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


# ============ 비동기 세션 (제한적 사용) ============

def _get_async_database_url() -> str:
    """
    동기 DATABASE_URL을 비동기 URL로 변환
    
    SQLite: sqlite:/// -> sqlite+aiosqlite:///
    PostgreSQL: postgresql:// -> postgresql+asyncpg://
    Oracle: oracle:// -> oracle+oracledb://
    """
    url = settings.DATABASE_URL

    # SQLite인 경우
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)

    # PostgreSQL인 경우
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)

    # Oracle인 경우
    if url.startswith("oracle://"):
        return url.replace("oracle://", "oracle+oracledb://", 1)

    # 이미 비동기 URL인 경우 그대로 반환
    if "+" in urlparse(url).scheme:
        return url

    logger.warning(f"Unknown database URL format: {url}, using as-is")
    return url


# 비동기 엔진 생성
async_database_url = _get_async_database_url()

# SQLite의 경우 connect_args 필요
async_connect_args = {}
if async_database_url.startswith("sqlite+aiosqlite"):
    async_connect_args = {"check_same_thread": False}

async_engine = create_async_engine(
    async_database_url,
    echo=settings.DEBUG,
    pool_size=settings.POOL_SIZE,
    max_overflow=settings.MAX_OVERFLOW,
    connect_args=async_connect_args,
)

# 비동기 Session factory
async_session_maker = async_sessionmaker(
    async_engine, class_=AsyncSession, expire_on_commit=False
)


async def init_db_async() -> None:
    """
    비동기 DB 테이블 자동 생성
    
    startup 시 호출되어 모든 SQLModel 테이블 생성
    """
    async with async_engine.begin() as conn:
        # 모든 모델 import (테이블 메타데이터 등록)
        from app.domain.holiday.model import HolidayModel, HolidayHashModel  # noqa: F401

        # 테이블 생성
        await conn.run_sync(SQLModel.metadata.create_all)
        logger.info("✅ Database tables initialized (async)")
