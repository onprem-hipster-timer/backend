"""
Schedule Dependencies

FastAPI Best Practices:
- Dependencies를 활용한 데이터 검증
- Chain Dependencies로 코드 재사용
- valid_schedule_id 패턴으로 중복 제거
"""
from uuid import UUID

from fastapi import Depends
from sqlmodel import Session

from app.crud import schedule as crud
from app.db.session import get_db
from app.domain.schedule.exceptions import ScheduleNotFoundError
from app.domain.schedule.model import Schedule


async def valid_schedule_id(
        schedule_id: UUID,
        session: Session = Depends(get_db),
) -> Schedule:
    """
    Schedule ID 검증 및 Schedule 반환

    FastAPI Best Practices:
    - Dependency로 데이터 검증
    - 여러 엔드포인트에서 재사용 가능
    - FastAPI가 결과를 캐싱하여 중복 호출 방지
    - 읽기 전용이므로 get_db 사용 (commit 불필요)

    :param schedule_id: Schedule ID
    :param session: DB 세션
    :return: Schedule 객체
    :raises ScheduleNotFoundError: 일정을 찾을 수 없는 경우
    """
    schedule = crud.get_schedule(session, schedule_id)
    if not schedule:
        raise ScheduleNotFoundError()
    return schedule
