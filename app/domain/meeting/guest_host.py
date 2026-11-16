"""
미팅의 게스트 호스트 (app/domain/guest/host.py)

| 상태 | 미팅 |
|------|------|
| MISSING | 없다 |
| EXPIRED | 게스트 기간이 끝났다. 기간은 미팅 시간대로 end_date + 31일 0시 전까지(end_date가 끝난 뒤 30일) |
| CLOSED | 게스트 허용(allow_guests)이 꺼져 있거나, 공개 범위가 PUBLIC이 아니거나, 소유자가 휴면 계정이다 |
| OPEN | 그 밖 |

소유자가 파기되면 미팅이 지워져 MISSING이다. 앱 시작 때 register로 등록한다 (app/main.py).

테스트: tests/domain/meeting/test_guest_host.py
"""
from datetime import datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlmodel import Session

from app.domain.dateutil.service import ensure_utc_naive
from app.domain.guest.host import GuestHostStatus, register_guest_host
from app.domain.visibility.enums import ResourceType
from app.domain.visibility.service import is_public
from app.models.base import utc_now_naive
from app.models.meeting import Meeting

# end_date가 끝난 뒤 게스트가 남는 날 수
GUEST_DAYS_AFTER_END = 30


def guest_period_end(meeting: Meeting) -> datetime:
    """게스트 기간이 끝나는 시각 (UTC naive): 미팅 시간대로 end_date + 31일 0시"""
    end_day = meeting.end_date + timedelta(days=GUEST_DAYS_AFTER_END + 1)
    return ensure_utc_naive(datetime.combine(end_day, time(0), ZoneInfo(meeting.timezone)))


class MeetingGuestHost:
    def guest_status(self, session: Session, resource_id: UUID) -> GuestHostStatus:
        meeting = session.get(Meeting, resource_id)
        if meeting is None:
            return GuestHostStatus.MISSING
        if utc_now_naive() >= guest_period_end(meeting):
            return GuestHostStatus.EXPIRED
        if not meeting.allow_guests or not is_public(session, ResourceType.MEETING, meeting.id, meeting.owner_id):
            return GuestHostStatus.CLOSED
        return GuestHostStatus.OPEN


def register() -> None:
    register_guest_host(ResourceType.MEETING, MeetingGuestHost())
