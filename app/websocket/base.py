"""
WebSocket 공용 스키마

도메인 무관한 WebSocket 인프라 레벨 메시지 구조 정의
"""
from datetime import datetime
from enum import Enum
from typing import Optional, Any

from pydantic import BaseModel, Field


class WSMessageType(str, Enum):
    """WebSocket 공용 메시지 타입"""
    # 공용 타입
    ERROR = "error"
    CONNECTED = "connected"


class WSClientMessage(BaseModel):
    """클라이언트 -> 서버 메시지 (공용)"""
    type: str  # 도메인별로 다른 타입 사용 가능
    payload: dict[str, Any] = {}


class WSServerMessage(BaseModel):
    """서버 -> 클라이언트 메시지 (공용)"""
    type: str  # 도메인별로 다른 타입 사용 가능
    payload: dict[str, Any] = {}
    from_user: Optional[str] = None  # 메시지 발생 사용자 (동기화용)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    def to_json(self) -> str:
        """JSON 문자열로 변환"""
        return self.model_dump_json()


class ErrorPayload(BaseModel):
    """에러 응답 페이로드"""
    code: str
    message: str
    details: Optional[dict[str, Any]] = None
