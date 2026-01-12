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

from app.core.auth import CurrentUser, get_current_user
from app.crud import schedule as crud
from app.db.session import get_db
from app.domain.schedule.exceptions import ScheduleNotFoundError
from app.domain.schedule.model import Schedule
from app.models.schedule import ScheduleException


async def valid_schedule_id(
        schedule_id: UUID,
        session: Session = Depends(get_db),
        current_user: CurrentUser = Depends(get_current_user),
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
    :param current_user: 현재 인증된 사용자
    :return: Schedule 객체
    :raises ScheduleNotFoundError: 일정을 찾을 수 없는 경우
    """
    schedule = crud.get_schedule(session, schedule_id, current_user.sub)
    if not schedule:
        raise ScheduleNotFoundError()
    return schedule


async def valid_schedule_exception_id(
        exception_id: UUID,
        session: Session = Depends(get_db),
) -> ScheduleException:
    """
    ScheduleException ID 검증 및 ScheduleException 반환

    FastAPI Best Practices:
    - Dependency로 데이터 검증
    - 여러 엔드포인트에서 재사용 가능
    - FastAPI가 결과를 캐싱하여 중복 호출 방지
    - 읽기 전용이므로 get_db 사용 (commit 불필요)

    :param exception_id: ScheduleException ID
    :param session: DB 세션
    :return: ScheduleException 객체
    :raises ScheduleNotFoundError: 예외 일정을 찾을 수 없는 경우
    """
    from app.models.schedule import ScheduleException
    exception = session.get(ScheduleException, exception_id)
    if not exception:
        raise ScheduleNotFoundError()
    return exception
