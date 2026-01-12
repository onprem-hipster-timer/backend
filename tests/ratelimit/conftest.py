"""
레이트 리밋 테스트 전용 fixture

레이트 리밋 테스트에서만 사용되는 별도의 클라이언트 fixture.
기본 e2e_client와 완전히 분리되어 다른 테스트에 영향을 주지 않습니다.
"""
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine

from app.ratelimit.storage.memory import reset_storage


@pytest.fixture
def rate_limit_client():
    """
    레이트 리밋 활성화된 테스트 클라이언트
    
    특징:
    - 레이트 리밋 활성화 상태
    - 별도의 메모리 DB 인스턴스
    - 테스트 전후 저장소 초기화
    - 다른 테스트와 완전히 격리
    """
    # 1. 레이트 리밋 활성화
    original_rate_limit = os.environ.get("RATE_LIMIT_ENABLED", "false")
    os.environ["RATE_LIMIT_ENABLED"] = "true"
    
    # settings 재로드
    from app.core.config import Settings
    import app.core.config as config_module
    config_module.settings = Settings()
    
    # 저장소 초기화
    reset_storage()
    
    # 2. 별도의 테스트 DB 생성
    from app.db.session import _session_manager
    
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    
    @event.listens_for(test_engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    
    # 엔진 교체
    original_engine = _session_manager.engine
    _session_manager.engine = test_engine
    
    # 테이블 생성
    SQLModel.metadata.create_all(test_engine)
    
    # 3. TestClient 생성
    from app.main import app
    client = TestClient(app)
    
    yield client
    
    # 4. 정리
    # 엔진 복원
    _session_manager.engine = original_engine
    SQLModel.metadata.drop_all(test_engine)
    test_engine.dispose()
    
    # 레이트 리밋 비활성화 복원
    os.environ["RATE_LIMIT_ENABLED"] = original_rate_limit
    config_module.settings = Settings()
    reset_storage()
