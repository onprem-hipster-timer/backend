# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Hipster Timer Project Contributors

import logging
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator
from urllib.parse import urlparse

from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlmodel import SQLModel, create_engine, Session

from app.core.config import settings

logger = logging.getLogger(__name__)


def _is_sqlite() -> bool:
    """SQLite 데이터베이스 여부 확인"""
    return settings.DATABASE_URL.startswith("sqlite")


def _is_postgresql() -> bool:
    """PostgreSQL 데이터베이스 여부 확인"""
    return settings.DATABASE_URL.startswith("postgresql")


class SessionManager:
    """세션 관리자 - Context Manager 패턴"""

    def __init__(self):
        self.engine = None
        self._init_engine()

    def _init_engine(self):
        """엔진 초기화 - DB 타입에 따라 최적화된 설정 적용"""
        if _is_sqlite():
            self._init_sqlite_engine()
        elif _is_postgresql():
            self._init_postgresql_engine()
        else:
            # 기타 DB: 기본 설정으로 생성
            self._init_default_engine()

    def _init_sqlite_engine(self):
        """SQLite 엔진 초기화"""
        connect_args = {"check_same_thread": False}

        self.engine = create_engine(
            settings.DATABASE_URL,
            echo=settings.DEBUG,
            connect_args=connect_args,
        )

        # SQLite 외래 키 제약 조건 활성화 (각 연결마다)
        @event.listens_for(self.engine, "connect")
        def set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        logger.info("✅ SQLite engine initialized")

    def _init_postgresql_engine(self):
        """PostgreSQL 엔진 초기화 - 프로덕션 최적화 설정"""
        self.engine = create_engine(
            settings.DATABASE_URL,
            echo=settings.DEBUG,
            pool_size=settings.POOL_SIZE,
            max_overflow=settings.MAX_OVERFLOW,
            pool_pre_ping=settings.DB_POOL_PRE_PING,  # 연결 유효성 검사
            pool_recycle=settings.DB_POOL_RECYCLE,  # 연결 재활용 시간
        )

        logger.info("✅ PostgreSQL engine initialized (pool_size=%d, pool_pre_ping=%s)",
                    settings.POOL_SIZE, settings.DB_POOL_PRE_PING)

    def _init_default_engine(self):
        """기본 엔진 초기화 (기타 DB)"""
        self.engine = create_engine(
            settings.DATABASE_URL,
            echo=settings.DEBUG,
            pool_size=settings.POOL_SIZE,
            max_overflow=settings.MAX_OVERFLOW,
            pool_pre_ping=settings.DB_POOL_PRE_PING,
            pool_recycle=settings.DB_POOL_RECYCLE,
        )

        logger.info("✅ Database engine initialized: %s", settings.DATABASE_URL.split("://")[0])

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


def _create_async_engine():
    """비동기 엔진 생성 - DB 타입에 따라 최적화된 설정 적용"""
    async_url = _get_async_database_url()

    if _is_sqlite():
        # SQLite: connect_args 필요, pool 설정 불필요
        return create_async_engine(
            async_url,
            echo=settings.DEBUG,
            connect_args={"check_same_thread": False},
        )
    elif _is_postgresql():
        # PostgreSQL: 프로덕션 최적화 설정
        return create_async_engine(
            async_url,
            echo=settings.DEBUG,
            pool_size=settings.POOL_SIZE,
            max_overflow=settings.MAX_OVERFLOW,
            pool_pre_ping=settings.DB_POOL_PRE_PING,
            pool_recycle=settings.DB_POOL_RECYCLE,
        )
    else:
        # 기타 DB: 기본 설정
        return create_async_engine(
            async_url,
            echo=settings.DEBUG,
            pool_size=settings.POOL_SIZE,
            max_overflow=settings.MAX_OVERFLOW,
            pool_pre_ping=settings.DB_POOL_PRE_PING,
            pool_recycle=settings.DB_POOL_RECYCLE,
        )


# 비동기 엔진 생성
async_engine = _create_async_engine()

# 비동기 Session factory
async_session_maker = async_sessionmaker(
    async_engine, class_=AsyncSession, expire_on_commit=False
)


@asynccontextmanager
async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """
    비동기 트랜잭션 자동 관리 세션
    - Background tasks 등에서 사용
    - 함수 종료 성공: commit 자동
    - 예외 발생: rollback 자동
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


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
