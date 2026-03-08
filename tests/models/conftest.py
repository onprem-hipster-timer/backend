"""
tests/models 전용 테스트 모델

실제 도메인 모델에 의존하지 않고 base.py(UUIDBase, TimestampMixin, UpdateMixin)를
독립적으로 테스트하기 위한 더미 모델.
"""
from typing import Optional

import pytest
from sqlmodel import Field

from app.models.base import UUIDBase, TimestampMixin


class FakeModel(UUIDBase, TimestampMixin, table=True):
    """base.py 테스트 전용 더미 모델"""
    __tablename__ = "fake_model"

    owner_id: str = Field(default="test-user")
    name: str = Field(default="original")
    description: Optional[str] = Field(default=None)
    score: int = Field(default=0)


@pytest.fixture
def fake_model():
    """기본 FakeModel 인스턴스"""
    return FakeModel(
        owner_id="test-user",
        name="original",
        description="original desc",
        score=10,
    )
