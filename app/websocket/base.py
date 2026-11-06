"""
WebSocket 공용 스키마

도메인 무관한 WebSocket 인프라 레벨 메시지 구조 정의
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Any
from uuid import uuid4

from pydantic import Field

from app.core.base_model import CustomModel


class WSMessageType(str, Enum):
    """WebSocket 공용 메시지 타입"""
    CONNECTED = "connected"


class WSServerMessage(CustomModel):
    """서버 -> 클라이언트 메시지 봉투 (실시간 두 모드 공통 계약: docs/api/websocket.ko.md)

    시각은 REST 응답과 같은 형식(`2026-11-06T10:30:00+0000`)으로 직렬화된다 (CustomModel)
    """
    id: str = Field(default_factory=lambda: str(uuid4()))  # 메시지 ID (클라이언트가 중복 제거에 쓴다)
    type: str  # 도메인별로 다른 타입 사용 가능
    payload: dict[str, Any] = {}
    from_user: Optional[str] = None  # 메시지 발생 사용자 (동기화용)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))  # UTC aware

    def to_json(self) -> str:
        """JSON 문자열로 변환"""
        return self.model_dump_json()
