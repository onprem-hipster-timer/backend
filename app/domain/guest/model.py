"""
Guest Domain Model

ORM 모델(app/models/guest.py)을 도메인에서 쓰도록 다시 내보낸다.
"""
from app.models.guest import Guest

__all__ = ["Guest"]
