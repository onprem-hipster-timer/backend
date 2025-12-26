from typing import Generator
from sqlmodel import Session
from app.db.session import SessionManager

session_manager = SessionManager()


def get_db_transactional() -> Generator[Session, None, None]:
    """
    Context Manager를 통한 트랜잭션 자동 관리
    - FastAPI Depends와 함께 사용
    - 함수 종료 성공: commit 자동
    - 예외 발생: rollback 자동
    """
    session = None
    try:
        with session_manager.get_session() as session:
            yield session
            session.commit()
    except Exception:
        if session:
            session.rollback()
        raise
    finally:
        if session:
            session.close()


def get_session() -> Generator[Session, None, None]:
    """기본 세션 (트랜잭션 수동 관리)"""
    with session_manager.get_session() as session:
        yield session

