"""
타이머 만료

RUNNING 타이머는 expires_at = started_at + (allocated_duration - elapsed_time)에 만료된다.
만료 표현: status=PAUSED, elapsed_time=allocated_duration, paused_at=expires_at,
pause_history에 {"action": "expire", "at": expires_at, "elapsed": allocated_duration}.

- 조회는 이 표현을 응답에만 적용하고 행은 쓰지 않는다 (TimerRead.from_model)
- 명령은 처리 전에 행에 확정한다 (TimerService._materialize_expiry)

규칙: docs/guides/timer.ko.md
테스트: tests/test_timers_expiry.py, tests/test_timers_read_no_write.py
"""
from datetime import datetime, timedelta
from typing import Any, TYPE_CHECKING

from app.core.constants import TimerStatus

if TYPE_CHECKING:
    from app.domain.timer.model import TimerSession


def expires_at(timer: "TimerSession") -> datetime | None:
    """RUNNING이고 started_at이 있을 때만 만료 시각 (UTC naive)"""
    if timer.status != TimerStatus.RUNNING.value or timer.started_at is None:
        return None
    return timer.started_at + timedelta(seconds=timer.allocated_duration - timer.elapsed_time)


def expired_fields(timer: "TimerSession", now: datetime) -> dict[str, Any] | None:
    """now(UTC naive)에 만료됐으면 만료 표현의 필드 값, 아니면 None. timer는 바꾸지 않는다"""
    at = expires_at(timer)
    if at is None or now < at:
        return None
    history = list(timer.pause_history) if timer.pause_history else []
    history.append({"action": "expire", "at": at.isoformat(), "elapsed": timer.allocated_duration})
    return {
        "status": TimerStatus.PAUSED.value,
        "elapsed_time": timer.allocated_duration,
        "paused_at": at,
        "pause_history": history,
    }
