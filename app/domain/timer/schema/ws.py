"""
타이머 WebSocket 메시지 스키마

Timer 도메인 전용 WebSocket 메시지 구조 정의
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.dateutil.service import convert_utc_naive_to_timezone, ensure_utc_naive


class TimerWSMessageType(str, Enum):
    """타이머 WebSocket 메시지 타입"""
    # 클라이언트 -> 서버
    CREATE = "timer.create"
    PAUSE = "timer.pause"
    RESUME = "timer.resume"
    STOP = "timer.stop"
    SYNC = "timer.sync"

    # 서버 -> 클라이언트
    CREATED = "timer.created"
    UPDATED = "timer.updated"
    DELETED = "timer.deleted"
    SYNC_RESULT = "timer.sync_result"  # 타이머 목록 동기화 결과
    FRIEND_ACTIVITY = "timer.friend_activity"


class TimerAction(str, Enum):
    """타이머 액션 타입"""
    START = "start"
    PAUSE = "pause"
    RESUME = "resume"
    STOP = "stop"


# ============================================================
# 클라이언트 -> 서버 페이로드
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
    timer_id: Optional[UUID] = None  # None이면 활성 타이머 목록 동기화
    scope: Optional[str] = "active"  # active(활성만), all(전체)


# ============================================================
# 서버 -> 클라이언트 페이로드
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

    model_config = ConfigDict(from_attributes=True)

    def to_timezone(self, tz: timezone | str | None) -> "TimerData":
        """
        UTC naive datetime 필드를 지정된 타임존의 aware datetime으로 변환
        
        :param tz: 타임존 (timezone 객체, 문자열, 또는 None)
        :return: 타임존이 변환된 새로운 TimerData 인스턴스
        """
        if tz is None:
            return self
        
        # datetime 필드 변환
        update_data = {}
        for field_name in ["started_at", "paused_at", "ended_at", "created_at", "updated_at"]:
            value = getattr(self, field_name, None)
            if value is not None and isinstance(value, datetime):
                naive_value = ensure_utc_naive(value)
                update_data[field_name] = convert_utc_naive_to_timezone(naive_value, tz)
        
        # pause_history의 타임스탬프 변환
        if self.pause_history:
            converted_history = []
            for event in self.pause_history:
                event_copy = event.copy()
                if "at" in event_copy and event_copy["at"]:
                    # ISO 문자열을 datetime으로 파싱
                    if isinstance(event_copy["at"], str):
                        at_dt = datetime.fromisoformat(event_copy["at"].replace("Z", "+00:00"))
                    else:
                        at_dt = event_copy["at"]
                    at_naive = ensure_utc_naive(at_dt)
                    converted_at = convert_utc_naive_to_timezone(at_naive, tz)
                    event_copy["at"] = converted_at.isoformat()
                converted_history.append(event_copy)
            update_data["pause_history"] = converted_history
        
        # model_copy를 사용하여 새 인스턴스 생성
        return self.model_copy(update=update_data)


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


class TimerSyncResultPayload(BaseModel):
    """타이머 동기화 결과 페이로드"""
    timers: list[TimerData]
    count: int
