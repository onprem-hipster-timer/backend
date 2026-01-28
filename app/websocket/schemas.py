"""
WebSocket 메시지 스키마

클라이언트-서버 간 WebSocket 메시지 구조 정의
"""
from datetime import datetime
from enum import Enum
from typing import Optional, Any
from uuid import UUID

from pydantic import BaseModel, Field


class WSMessageType(str, Enum):
    """WebSocket 메시지 타입"""
    # 클라이언트 -> 서버
    TIMER_CREATE = "timer.create"
    TIMER_PAUSE = "timer.pause"
    TIMER_RESUME = "timer.resume"
    TIMER_STOP = "timer.stop"
    TIMER_SYNC = "timer.sync"  # 현재 상태 동기화 요청

    # 서버 -> 클라이언트
    TIMER_UPDATED = "timer.updated"
    TIMER_CREATED = "timer.created"
    TIMER_DELETED = "timer.deleted"
    TIMER_FRIEND_ACTIVITY = "timer.friend_activity"
    ERROR = "error"
    CONNECTED = "connected"


class TimerAction(str, Enum):
    """타이머 액션 타입"""
    START = "start"
    PAUSE = "pause"
    RESUME = "resume"
    STOP = "stop"


# ============================================================
# 클라이언트 -> 서버 메시지
# ============================================================

class TimerCreatePayload(BaseModel):
    """타이머 생성 페이로드"""
    schedule_id: Optional[UUID] = None
    todo_id: Optional[UUID] = None
    title: Optional[str] = None
    description: Optional[str] = None
    allocated_duration: int = Field(..., gt=0, description="할당 시간 (초)")
    tag_ids: Optional[list[UUID]] = None


class TimerActionPayload(BaseModel):
    """타이머 액션 페이로드 (pause, resume, stop)"""
    timer_id: UUID


class TimerSyncPayload(BaseModel):
    """타이머 동기화 요청 페이로드"""
    timer_id: Optional[UUID] = None  # None이면 전체 활성 타이머 동기화


class WSClientMessage(BaseModel):
    """클라이언트 -> 서버 메시지"""
    type: WSMessageType
    payload: dict[str, Any] = {}


# ============================================================
# 서버 -> 클라이언트 메시지
# ============================================================

class TimerData(BaseModel):
    """타이머 데이터 (응답용)"""
    id: UUID
    schedule_id: Optional[UUID] = None
    todo_id: Optional[UUID] = None
    title: Optional[str] = None
    description: Optional[str] = None
    allocated_duration: int
    elapsed_time: int
    status: str
    started_at: Optional[datetime] = None
    paused_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    pause_history: list[dict[str, Any]] = []
    created_at: datetime
    updated_at: datetime
    owner_id: str

    class Config:
        from_attributes = True


class TimerUpdatedPayload(BaseModel):
    """타이머 업데이트 응답 페이로드"""
    timer: TimerData
    action: TimerAction


class FriendActivityPayload(BaseModel):
    """친구 활동 알림 페이로드"""
    friend_id: str
    action: TimerAction
    timer_id: UUID
    timer_title: Optional[str] = None


class ErrorPayload(BaseModel):
    """에러 응답 페이로드"""
    code: str
    message: str
    details: Optional[dict[str, Any]] = None


class WSServerMessage(BaseModel):
    """서버 -> 클라이언트 메시지"""
    type: WSMessageType
    payload: dict[str, Any] = {}
    from_user: Optional[str] = None  # 메시지 발생 사용자 (동기화용)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    def to_json(self) -> str:
        """JSON 문자열로 변환"""
        return self.model_dump_json()
