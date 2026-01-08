"""
Todo Domain Model

아키텍처 원칙:
- Todo는 Schedule 테이블을 공유
- Domain 레이어에서만 분리하여 관심사 분리
"""
from app.models.schedule import Schedule as ScheduleModel

# Todo는 Schedule 모델을 재사용
Todo = ScheduleModel

