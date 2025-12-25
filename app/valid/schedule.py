from datetime import datetime

from sqlalchemy import event

from app.models.schedule import Schedule


def validate_time_order(start_time: datetime | None, end_time: datetime | None):
    """
    :param start_time: 시작 날짜
    :param end_time: 종료 날짜
    :return: 시작 날짜 <= 종료 날짜
    """
    if start_time is not None and end_time is not None:
        if end_time <= start_time:
            raise ValueError("end_time must be after start_time")


def _validate_time_order(mapper, connection, target):
    """
    DB 검증용 리스너
    :param mapper: pass
    :param connection: pass
    :param target: entity parm
    :return:
    """
    validate_time_order(target.start_time, target.end_time)


event.listen(Schedule, "before_insert", _validate_time_order)
event.listen(Schedule, "before_update", _validate_time_order)
