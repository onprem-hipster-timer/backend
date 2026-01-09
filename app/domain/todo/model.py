"""
Todo Domain Model

아키텍처 원칙:
- Todo는 독립적인 모델
- Domain 레이어에서 ORM 모델을 직접 사용
"""
from app.models.todo import Todo as TodoModel

# Domain 모델은 ORM 모델과 동일하게 사용
Todo = TodoModel

