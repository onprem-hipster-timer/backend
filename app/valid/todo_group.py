"""
TodoGroup Validators

DB 레벨 검증을 위한 SQLAlchemy Event Listeners
"""
from sqlalchemy import event

from app.models.todo_group import TodoGroup
from app.utils.validators import validate_color


def _validate_todo_group_color(mapper, connection, target):
    """할 일 그룹 색상 검증용 리스너"""
    validate_color(target.color)


event.listen(TodoGroup, "before_insert", _validate_todo_group_color)
event.listen(TodoGroup, "before_update", _validate_todo_group_color)
