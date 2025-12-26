from sqlalchemy import event

from app.models.schedule import Schedule
from app.utils.validators import validate_time_order


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
