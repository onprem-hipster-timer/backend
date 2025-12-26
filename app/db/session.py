from sqlmodel import SQLModel, create_engine, Session
from contextlib import contextmanager
from app.core.config import settings


class SessionManager:
    """세션 관리자 - Context Manager 패턴"""
    
    def __init__(self):
        self.engine = None
        self._init_engine()
    
    def _init_engine(self):
        """엔진 초기화"""
        self.engine = create_engine(
            settings.DATABASE_URL,
            echo=settings.DEBUG,
            pool_size=settings.POOL_SIZE,
            max_overflow=settings.MAX_OVERFLOW,
        )
    
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


def get_session():
    """의존성으로 사용되는 세션"""
    with _session_manager.get_session() as session:
        yield session
