"""
Tag CRUD Operations

아키텍처 원칙:
- CRUD는 단순 데이터베이스 작업만 수행
- 비즈니스 로직은 Service에서 처리
- commit은 get_db_transactional이 처리
"""
from typing import List, Optional
from uuid import UUID

from sqlmodel import Session, select

from app.models.tag import TagGroup, Tag, ScheduleTag, ScheduleExceptionTag, TimerTag


# ============================================================
# TagGroup CRUD
# ============================================================

def create_tag_group(session: Session, tag_group: TagGroup) -> TagGroup:
    """태그 그룹 생성"""
    session.add(tag_group)
    session.flush()  # ID를 얻기 위해 flush
    session.refresh(tag_group)
    return tag_group


def get_tag_group(session: Session, group_id: UUID) -> Optional[TagGroup]:
    """태그 그룹 조회"""
    return session.get(TagGroup, group_id)


def get_all_tag_groups(session: Session) -> List[TagGroup]:
    """모든 태그 그룹 조회"""
    statement = select(TagGroup).order_by(TagGroup.name)
    return list(session.exec(statement).all())


def update_tag_group(session: Session, tag_group: TagGroup) -> TagGroup:
    """태그 그룹 업데이트"""
    session.add(tag_group)
    session.flush()  # ID를 얻기 위해 flush
    session.refresh(tag_group)
    return tag_group


def delete_tag_group(session: Session, tag_group: TagGroup) -> None:
    """태그 그룹 삭제"""
    session.delete(tag_group)
    # commit은 get_db_transactional이 처리


# ============================================================
# Tag CRUD
# ============================================================

def create_tag(session: Session, tag: Tag) -> Tag:
    """태그 생성"""
    session.add(tag)
    session.flush()  # ID를 얻기 위해 flush
    session.refresh(tag)
    return tag


def get_tag(session: Session, tag_id: UUID) -> Optional[Tag]:
    """태그 조회"""
    return session.get(Tag, tag_id)


def get_tags_by_group(session: Session, group_id: UUID) -> List[Tag]:
    """그룹별 태그 조회"""
    statement = select(Tag).where(Tag.group_id == group_id).order_by(Tag.name)
    return list(session.exec(statement).all())


def get_all_tags(session: Session) -> List[Tag]:
    """모든 태그 조회"""
    statement = select(Tag).order_by(Tag.name)
    return list(session.exec(statement).all())


def get_tag_by_name_in_group(session: Session, group_id: UUID, name: str) -> Optional[Tag]:
    """그룹 내 이름으로 태그 조회"""
    statement = select(Tag).where(Tag.group_id == group_id, Tag.name == name)
    return session.exec(statement).first()


def update_tag(session: Session, tag: Tag) -> Tag:
    """태그 업데이트"""
    session.add(tag)
    session.flush()  # ID를 얻기 위해 flush
    session.refresh(tag)
    return tag


def delete_tag(session: Session, tag: Tag) -> None:
    """태그 삭제"""
    session.delete(tag)
    # commit은 get_db_transactional이 처리


# ============================================================
# Schedule-Tag 관계 CRUD
# ============================================================

def add_schedule_tag(session: Session, schedule_id: UUID, tag_id: UUID) -> ScheduleTag:
    """일정에 태그 추가"""
    schedule_tag = ScheduleTag(schedule_id=schedule_id, tag_id=tag_id)
    session.add(schedule_tag)
    session.flush()  # ID를 얻기 위해 flush
    session.refresh(schedule_tag)
    return schedule_tag


def get_schedule_tag(session: Session, schedule_id: UUID, tag_id: UUID) -> Optional[ScheduleTag]:
    """일정-태그 관계 조회"""
    statement = select(ScheduleTag).where(
        ScheduleTag.schedule_id == schedule_id,
        ScheduleTag.tag_id == tag_id
    )
    return session.exec(statement).first()


def get_schedule_tags(session: Session, schedule_id: UUID) -> List[Tag]:
    """일정의 모든 태그 조회"""
    statement = (
        select(Tag)
        .join(ScheduleTag)
        .where(ScheduleTag.schedule_id == schedule_id)
        .order_by(Tag.name)
    )
    return list(session.exec(statement).all())


def delete_schedule_tag(session: Session, schedule_tag: ScheduleTag) -> None:
    """일정에서 태그 제거"""
    session.delete(schedule_tag)
    # commit은 get_db_transactional이 처리


def delete_all_schedule_tags(session: Session, schedule_id: UUID) -> None:
    """일정의 모든 태그 제거"""
    statement = select(ScheduleTag).where(ScheduleTag.schedule_id == schedule_id)
    schedule_tags = session.exec(statement).all()
    for st in schedule_tags:
        session.delete(st)
    # commit은 get_db_transactional이 처리


# ============================================================
# ScheduleException-Tag 관계 CRUD
# ============================================================

def add_schedule_exception_tag(
        session: Session, exception_id: UUID, tag_id: UUID
) -> ScheduleExceptionTag:
    """예외 일정에 태그 추가"""
    exception_tag = ScheduleExceptionTag(schedule_exception_id=exception_id, tag_id=tag_id)
    session.add(exception_tag)
    session.flush()  # ID를 얻기 위해 flush
    session.refresh(exception_tag)
    return exception_tag


def get_schedule_exception_tag(
        session: Session, exception_id: UUID, tag_id: UUID
) -> Optional[ScheduleExceptionTag]:
    """예외 일정-태그 관계 조회"""
    statement = select(ScheduleExceptionTag).where(
        ScheduleExceptionTag.schedule_exception_id == exception_id,
        ScheduleExceptionTag.tag_id == tag_id
    )
    return session.exec(statement).first()


def get_schedule_exception_tags(session: Session, exception_id: UUID) -> List[Tag]:
    """예외 일정의 모든 태그 조회"""
    statement = (
        select(Tag)
        .join(ScheduleExceptionTag)
        .where(ScheduleExceptionTag.schedule_exception_id == exception_id)
        .order_by(Tag.name)
    )
    return list(session.exec(statement).all())


def delete_schedule_exception_tag(session: Session, exception_tag: ScheduleExceptionTag) -> None:
    """예외 일정에서 태그 제거"""
    session.delete(exception_tag)
    # commit은 get_db_transactional이 처리


def delete_all_schedule_exception_tags(session: Session, exception_id: UUID) -> None:
    """예외 일정의 모든 태그 제거"""
    statement = select(ScheduleExceptionTag).where(
        ScheduleExceptionTag.schedule_exception_id == exception_id
    )
    exception_tags = session.exec(statement).all()
    for et in exception_tags:
        session.delete(et)
    # commit은 get_db_transactional이 처리


# ============================================================
# Timer-Tag 관계 CRUD
# ============================================================

def add_timer_tag(session: Session, timer_id: UUID, tag_id: UUID) -> TimerTag:
    """타이머에 태그 추가"""
    timer_tag = TimerTag(timer_id=timer_id, tag_id=tag_id)
    session.add(timer_tag)
    session.flush()  # ID를 얻기 위해 flush
    session.refresh(timer_tag)
    return timer_tag


def get_timer_tag(session: Session, timer_id: UUID, tag_id: UUID) -> Optional[TimerTag]:
    """타이머-태그 관계 조회"""
    statement = select(TimerTag).where(
        TimerTag.timer_id == timer_id,
        TimerTag.tag_id == tag_id
    )
    return session.exec(statement).first()


def get_timer_tags(session: Session, timer_id: UUID) -> List[Tag]:
    """타이머의 모든 태그 조회"""
    statement = (
        select(Tag)
        .join(TimerTag)
        .where(TimerTag.timer_id == timer_id)
        .order_by(Tag.name)
    )
    return list(session.exec(statement).all())


def delete_timer_tag(session: Session, timer_tag: TimerTag) -> None:
    """타이머에서 태그 제거"""
    session.delete(timer_tag)
    # commit은 get_db_transactional이 처리


def delete_all_timer_tags(session: Session, timer_id: UUID) -> None:
    """타이머의 모든 태그 제거"""
    statement = select(TimerTag).where(TimerTag.timer_id == timer_id)
    timer_tags = session.exec(statement).all()
    for tt in timer_tags:
        session.delete(tt)
    # commit은 get_db_transactional이 처리
