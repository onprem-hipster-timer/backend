"""
UUIDBase Tests
"""
import uuid

from tests.models.conftest import FakeModel


def test_uuid_generated_on_creation():
    """인스턴스 생성 시 UUID 자동 할당"""
    entity = FakeModel()

    assert isinstance(entity.id, uuid.UUID)


def test_uuid_unique_per_instance():
    """인스턴스마다 고유 UUID 생성"""
    a = FakeModel()
    b = FakeModel()

    assert a.id != b.id


def test_uuid_accepts_explicit_id():
    """명시적 UUID 주입 허용"""
    explicit_id = uuid.uuid4()
    entity = FakeModel(id=explicit_id)

    assert entity.id == explicit_id
