"""
타이머 실시간 메시지 스키마

서버 -> 클라이언트 이벤트의 type·action과 payload.timer(TimerData).
봉투 조립: app/domain/timer/realtime.py
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domain.dateutil.service import convert_utc_naive_to_timezone, ensure_utc_naive
from app.domain.timer.schema.dto import pause_history_to_timezone


class TimerWSMessageType(str, Enum):
    """타이머 이벤트 타입 (서버 -> 클라이언트)"""
    CREATED = "timer.created"
    UPDATED = "timer.updated"
    DELETED = "timer.deleted"


class TimerAction(str, Enum):
    """타이머 액션 타입"""
    START = "start"
    PAUSE = "pause"
    RESUME = "resume"
    STOP = "stop"
    CANCEL = "cancel"
    UPDATE = "update"
    DELETE = "delete"


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
            update_data["pause_history"] = pause_history_to_timezone(self.pause_history, tz)

        # model_copy를 사용하여 새 인스턴스 생성
        return self.model_copy(update=update_data)
