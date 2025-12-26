from typing import Generator

from sqlmodel import Session

from app.db.session import _session_manager


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


def get_session() -> Generator[Session, None, None]:
    """기본 세션 (트랜잭션 수동 관리)"""
    with _session_manager.get_session() as session:
        yield session
