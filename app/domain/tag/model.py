"""
Tag Domain Model

아키텍처 원칙:
- Domain 모델은 ORM 모델과 동일 (현실적 협의안)
- 비즈니스 로직은 Service 계층에서 처리
"""
from app.models.tag import (
    TagGroup as TagGroupModel,
    Tag as TagModel,
    ScheduleTag as ScheduleTagModel,
    ScheduleExceptionTag as ScheduleExceptionTagModel,
)

# Domain 모델은 ORM 모델과 동일하게 사용
TagGroup = TagGroupModel
Tag = TagModel
ScheduleTag = ScheduleTagModel
ScheduleExceptionTag = ScheduleExceptionTagModel
