from datetime import datetime
from uuid import UUID

from sqlmodel import Session, select

from app.domain.dateutil.service import get_datetime_range
from app.domain.schedule.schema.dto import ScheduleCreate, ScheduleUpdate
from app.models.schedule import Schedule, ScheduleException


def create_schedule(session: Session, data: ScheduleCreate, owner_id: str) -> Schedule:
    """
    새 Schedule을 DB에 생성합니다.
    
    FastAPI Best Practices:
    - commit은 get_db_transactional이 처리
    - CRUD는 데이터 접근만 담당
    
    :param session: DB 세션
    :param data: 일정 생성 데이터
    :param owner_id: 소유자 ID (OIDC sub claim)
    """
    schedule_data = data.model_dump()
    schedule_data['owner_id'] = owner_id
    schedule = Schedule.model_validate(schedule_data)
    session.add(schedule)
    # commit은 get_db_transactional이 처리
    session.flush()  # ID를 얻기 위해 flush
    session.refresh(schedule)
    return schedule


def get_schedules(session: Session, owner_id: str) -> list[Schedule]:
    """
    소유자의 모든 Schedule 객체를 조회합니다.
    """
    statement = select(Schedule).where(Schedule.owner_id == owner_id)
    results = session.exec(statement)
    return results.all()


def get_schedules_by_date_range(
        session: Session,
        start_date: datetime,
        end_date: datetime,
        owner_id: str,
) -> list[Schedule]:
    """
    [start_date, end_date) 범위와 겹치는 Schedule 객체를 조회합니다.

    일정 구간 [start_time, end_time)과 범위가 겹치는 조건: start_time < end_date AND end_time > start_date

    :param session: DB 세션
    :param start_date: 범위 시작 (포함)
    :param end_date: 범위 끝 (제외)
    :param owner_id: 소유자 ID
    :return: 해당 날짜 범위와 겹치는 모든 일정
    """
    statement = (
        select(Schedule)
        .where(Schedule.owner_id == owner_id)
        .where(Schedule.start_time < end_date)
        .where(Schedule.end_time > start_date)
        .order_by(Schedule.start_time)
    )
    results = session.exec(statement)
    return results.all()


def get_schedule(
        session: Session,
        schedule_id: UUID,
        owner_id: str,
        for_update: bool = False,
) -> Schedule | None:
    """
    ID로 Schedule 조회 (owner_id 검증 포함, 없으면 None 반환)

    for_update=True면 트랜잭션 끝까지 행을 잠그고(FOR NO KEY UPDATE, SQLite에서는 무시),
    세션에 이미 올라온 객체도 잠근 뒤의 DB 값으로 덮어쓴다.
    """
    statement = (
        select(Schedule)
        .where(Schedule.id == schedule_id)
        .where(Schedule.owner_id == owner_id)
    )
    if for_update:
        statement = statement.with_for_update(key_share=True).execution_options(
            populate_existing=True
        )
    return session.exec(statement).first()


def get_schedule_by_id(session: Session, schedule_id: UUID) -> Schedule | None:
    """
    ID로 Schedule 조회 (소유자 검증 없음 - 접근 제어는 Service에서 처리)
    
    공유 리소스 접근 시 사용
    """
    return session.get(Schedule, schedule_id)


def get_schedules_by_ids(session: Session, schedule_ids: list[UUID]) -> list[Schedule]:
    """
    여러 ID로 Schedule 배치 조회 (소유자 검증 없음)
    
    공유 리소스 조회 시 N+1 문제 방지를 위해 사용
    
    :param session: DB 세션
    :param schedule_ids: 조회할 Schedule ID 목록
    :return: Schedule 리스트
    """
    if not schedule_ids:
        return []
    statement = select(Schedule).where(Schedule.id.in_(schedule_ids))
    return list(session.exec(statement).all())


def update_schedule(
        session: Session,
        schedule: Schedule,
        data: ScheduleUpdate,
) -> Schedule:
    """
    Schedule 객체의 변경된 필드만 반영해 업데이트합니다.

    FastAPI Best Practices:
    - commit은 get_db_transactional이 처리
    """
    update_data = data.model_dump()
    schedule.apply_update(update_data)
    session.flush()
    session.refresh(schedule)
    return schedule


def update_schedule_exception(
        session: Session,
        exception: ScheduleException,
        update_data: dict,
) -> ScheduleException:
    """
    예외 인스턴스 필드 업데이트
    """
    exception.apply_update(update_data)
    session.flush()
    session.refresh(exception)
    return exception


def delete_schedule(session: Session, schedule: Schedule) -> None:
    """
    Schedule 객체를 삭제합니다.
    
    FastAPI Best Practices:
    - commit은 get_db_transactional이 처리
    """
    session.delete(schedule)
    # commit은 get_db_transactional이 처리


def get_recurring_schedules(
        session: Session,
        start_date: datetime,
        end_date: datetime,
        owner_id: str,
) -> list[Schedule]:
    """
    반복 일정을 조회합니다 (원본만, 가상 인스턴스 제외).
    
    반복 일정은 조회 범위와 겹칠 수 있는 모든 반복 일정을 반환합니다.
    
    :param session: DB 세션
    :param start_date: 범위 시작 (포함)
    :param end_date: 범위 끝 (제외)
    :param owner_id: 소유자 ID
    :return: 반복 일정 리스트 (recurrence_rule이 있는 일정)
    """
    statement = (
        select(Schedule)
        .where(Schedule.owner_id == owner_id)
        .where(Schedule.recurrence_rule.isnot(None))
        .where(
            # 첫 회차가 범위 끝 이전에 시작하고
            (Schedule.start_time < end_date)
        )
        .order_by(Schedule.start_time)
    )
    # 마지막 회차는 recurrence_end에 시작해 recurrence_end + 일정 길이에 끝날 수 있다
    # (일정 길이를 더하는 식은 DB마다 달라 메모리에서 거른다)
    return [
        s for s in session.exec(statement).all()
        if s.recurrence_end is None or s.recurrence_end + (s.end_time - s.start_time) > start_date
    ]


def get_schedule_exception(
        session: Session,
        exception_id: UUID,
        owner_id: str,
) -> ScheduleException | None:
    """
    ID로 예외 인스턴스를 조회합니다.
    
    :param session: DB 세션
    :param exception_id: 예외 인스턴스 ID
    :param owner_id: 소유자 ID
    :return: 예외 인스턴스 또는 None
    """
    statement = (
        select(ScheduleException)
        .where(ScheduleException.id == exception_id)
        .where(ScheduleException.owner_id == owner_id)
    )
    return session.exec(statement).first()


def get_schedule_exceptions(
        session: Session,
        start_date: datetime,
        end_date: datetime,
        owner_id: str,
) -> list[ScheduleException]:
    """
    exception_date(회차의 원래 시작 시각)가 [start_date, end_date)인 예외 인스턴스를 조회합니다.

    :param session: DB 세션
    :param start_date: 범위 시작 (포함)
    :param end_date: 범위 끝 (제외)
    :param owner_id: 소유자 ID
    :return: 예외 인스턴스 리스트
    """
    statement = (
        select(ScheduleException)
        .where(ScheduleException.owner_id == owner_id)
        .where(ScheduleException.exception_date >= start_date)
        .where(ScheduleException.exception_date < end_date)
    )
    results = session.exec(statement)
    return results.all()


def get_schedule_exceptions_by_parent_ids(
        session: Session,
        parent_ids: list[UUID],
        start_date: datetime,
        end_date: datetime,
) -> list[ScheduleException]:
    """
    지정한 반복 일정들의 exception_date가 [start_date, end_date)인 예외 인스턴스를 배치 조회합니다 (소유자 검증 없음).

    접근 권한이 확인된 일정의 ID만 넘겨야 합니다.

    :param session: DB 세션
    :param parent_ids: 원본 일정 ID 목록
    :param start_date: 범위 시작 (포함)
    :param end_date: 범위 끝 (제외)
    :return: 예외 인스턴스 리스트
    """
    if not parent_ids:
        return []
    statement = (
        select(ScheduleException)
        .where(ScheduleException.parent_id.in_(parent_ids))
        .where(ScheduleException.exception_date >= start_date)
        .where(ScheduleException.exception_date < end_date)
    )
    return list(session.exec(statement).all())


def get_schedule_exception_by_date(
        session: Session,
        parent_id: UUID,
        exception_date: datetime,
        owner_id: str,
) -> ScheduleException | None:
    """
    특정 인스턴스의 예외를 조회합니다.
    
    Bug Fix: 시간까지 비교하여 정확한 인스턴스 매칭
    - 날짜만 비교하면 하루에 여러 인스턴스가 있을 때 구분하지 못함
    - 시간까지 비교하여 정확한 인스턴스와 매칭 (1분 이내 허용 오차)
    
    :param session: DB 세션
    :param parent_id: 원본 일정 ID
    :param exception_date: 예외 날짜/시간
    :param owner_id: 소유자 ID
    :return: 예외 인스턴스 또는 None
    """
    # 시간까지 비교하기 위해 범위로 조회
    # 1분 이내 허용 오차
    start_range, end_range = get_datetime_range(exception_date)

    statement = (
        select(ScheduleException)
        .where(ScheduleException.owner_id == owner_id)
        .where(ScheduleException.parent_id == parent_id)
        .where(ScheduleException.exception_date >= start_range)
        .where(ScheduleException.exception_date <= end_range)
    )
    result = session.exec(statement).first()
    return result


def create_schedule_exception(
        session: Session,
        parent_id: UUID,
        exception_date: datetime,
        owner_id: str,
        is_deleted: bool = False,
        title: str | None = None,
        description: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
) -> ScheduleException:
    """
    예외 인스턴스를 생성합니다.
    
    :param session: DB 세션
    :param parent_id: 원본 일정 ID
    :param exception_date: 예외 날짜
    :param owner_id: 소유자 ID
    :param is_deleted: 삭제된 인스턴스인지
    :param title: 수정된 제목 (수정 시)
    :param description: 수정된 설명 (수정 시)
    :param start_time: 수정된 시작 시간 (수정 시)
    :param end_time: 수정된 종료 시간 (수정 시)
    :return: 생성된 예외 인스턴스
    """
    exception = ScheduleException(
        owner_id=owner_id,
        parent_id=parent_id,
        exception_date=exception_date,
        is_deleted=is_deleted,
        title=title,
        description=description,
        start_time=start_time,
        end_time=end_time,
    )
    session.add(exception)
    session.flush()
    session.refresh(exception)
    return exception


def get_schedules_by_source_todo_id(session: Session, todo_id: UUID, owner_id: str) -> list[Schedule]:
    """
    Todo에서 생성된 Schedule 조회
    
    :param session: DB 세션
    :param todo_id: Todo ID
    :param owner_id: 소유자 ID
    :return: 해당 Todo에서 생성된 Schedule 리스트
    """
    statement = (
        select(Schedule)
        .where(Schedule.owner_id == owner_id)
        .where(Schedule.source_todo_id == todo_id)
        .order_by(Schedule.start_time)
    )
    results = session.exec(statement)
    return list(results.all())
