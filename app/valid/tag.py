"""
Tag Validators

DB 레벨 검증을 위한 SQLAlchemy Event Listeners
"""
from sqlalchemy import event

from app.models.tag import Tag, TagGroup
from app.utils.validators import validate_color


def _validate_tag_color(mapper, connection, target):
    """
    Tag 색상 검증용 리스너
    
    :param mapper: pass
    :param connection: pass
    :param target: Tag entity
    :return:
    """
    validate_color(target.color)


def _validate_tag_group_color(mapper, connection, target):
    """
    TagGroup 색상 검증용 리스너
    
    :param mapper: pass
    :param connection: pass
    :param target: TagGroup entity
    :return:
    """
    validate_color(target.color)


# Tag 색상 검증
event.listen(Tag, "before_insert", _validate_tag_color)
event.listen(Tag, "before_update", _validate_tag_color)

# TagGroup 색상 검증
event.listen(TagGroup, "before_insert", _validate_tag_group_color)
event.listen(TagGroup, "before_update", _validate_tag_group_color)
