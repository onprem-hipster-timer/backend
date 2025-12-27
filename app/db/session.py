from contextlib import contextmanager
from typing import Generator

from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy import event

from app.core.config import settings


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


def get_db_transactional() -> Generator[Session, None, None]:
    """
    Context Manager를 통한 트랜잭션 자동 관리
    - FastAPI Depends와 함께 사용
    - 함수 종료 성공: commit 자동
    - 예외 발생: rollback 자동
    
    Bug Fix: 전역 싱글톤 _session_manager 사용
    Bug Fix: Context Manager 내부에서 commit/rollback 처리
    """
    session = None
    try:
        with _session_manager.get_session() as session:
            try:
                yield session
                # Context Manager 내부에서 commit (세션이 닫히기 전)
                session.commit()
            except Exception:
                # Context Manager 내부에서 rollback (세션이 닫히기 전)
                session.rollback()
                raise
    finally:
        # Context Manager가 자동으로 세션을 닫음
        pass


def get_db() -> Generator[Session, None, None]:
    """
    읽기 전용 세션 (commit 없음)
    - GET 요청 등 읽기 작업에 사용
    - FastAPI가 자동으로 세션 close 처리
    """
    with _session_manager.get_session() as session:
        yield session