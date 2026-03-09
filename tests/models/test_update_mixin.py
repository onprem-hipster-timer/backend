"""
UpdateMixin.apply_update Tests
"""
import uuid
from datetime import datetime

from pydantic.experimental.missing_sentinel import MISSING

from tests.models.conftest import FakeUpdateDTO


# ============================================================
# 일반 필드 업데이트
# ============================================================

def test_apply_update_regular_fields(fake_model):
    """일반 필드 업데이트 성공"""
    fake_model.apply_update({"name": "updated", "score": 99})

    assert fake_model.name == "updated"
    assert fake_model.score == 99


def test_apply_update_empty_data(fake_model):
    """빈 dict 전달 시 변경 없음"""
    fake_model.apply_update({})

    assert fake_model.name == "original"
    assert fake_model.score == 10


# ============================================================
# 보호 필드 (PK, owner_id, timestamps)
# ============================================================

def test_apply_update_protects_pk(fake_model):
    """PK(id) 변경 차단"""
    original_id = fake_model.id

    fake_model.apply_update({"id": uuid.uuid4()})

    assert fake_model.id == original_id


def test_apply_update_protects_owner_id(fake_model):
    """owner_id 변경 차단"""
    fake_model.apply_update({"owner_id": "hacker"})

    assert fake_model.owner_id == "test-user"


def test_apply_update_protects_created_at(fake_model):
    """created_at 변경 차단"""
    original = fake_model.created_at

    fake_model.apply_update({"created_at": datetime(2000, 1, 1)})

    assert fake_model.created_at == original


def test_apply_update_protects_updated_at(fake_model):
    """updated_at 변경 차단"""
    original = fake_model.updated_at

    fake_model.apply_update({"updated_at": datetime(2000, 1, 1)})

    assert fake_model.updated_at == original


# ============================================================
# nullable 처리
# ============================================================

def test_apply_update_allows_none_on_nullable_field(fake_model):
    """nullable 필드에 None 허용"""
    assert fake_model.description == "original desc"

    fake_model.apply_update({"description": None})

    assert fake_model.description is None


def test_apply_update_blocks_none_on_non_nullable_field(fake_model):
    """non-nullable 필드에 None 차단"""
    fake_model.apply_update({"name": None})

    assert fake_model.name == "original"


# ============================================================
# 기타 (unknown fields, custom exclude)
# ============================================================

def test_apply_update_ignores_unknown_fields(fake_model):
    """모델에 없는 필드 무시"""
    fake_model.apply_update({"nonexistent_field": "value"})

    assert fake_model.name == "original"


def test_apply_update_custom_exclude(fake_model):
    """exclude 파라미터로 추가 필드 제외"""
    fake_model.apply_update({"name": "updated"}, exclude=["name"])

    assert fake_model.name == "original"


# ============================================================
# MISSING sentinel 처리 - DTO model_dump() 경유 (정상 사용 경로)
# ============================================================

def test_apply_update_skips_missing_via_dto(fake_model):
    """DTO.model_dump()시 MISSING 필드는 자동 제외되어 업데이트 안됨"""
    dto = FakeUpdateDTO()  # 모든 필드가 MISSING
    fake_model.apply_update(dto.model_dump())

    assert fake_model.name == "original"
    assert fake_model.score == 10


def test_apply_update_partial_via_dto(fake_model):
    """DTO에서 일부 필드만 지정하면 해당 필드만 반영"""
    dto = FakeUpdateDTO(name="updated")  # description, score는 MISSING
    fake_model.apply_update(dto.model_dump())

    assert fake_model.name == "updated"
    assert fake_model.description == "original desc"
    assert fake_model.score == 10


def test_apply_update_missing_vs_none_via_dto(fake_model):
    """MISSING은 스킵, None은 nullable 필드에 적용"""
    dto = FakeUpdateDTO(description=None)  # name, score는 MISSING
    fake_model.apply_update(dto.model_dump())

    assert fake_model.name == "original"
    assert fake_model.description is None


def test_apply_update_all_missing_via_dto(fake_model):
    """모든 필드가 MISSING인 DTO → 아무것도 변경되지 않음"""
    dto = FakeUpdateDTO()
    fake_model.apply_update(dto.model_dump())

    assert fake_model.name == "original"
    assert fake_model.description == "original desc"
    assert fake_model.score == 10


# ============================================================
# MISSING sentinel 처리 - raw dict 직접 전달 (방어적 처리)
# apply_update는 model_dump() 없이 raw dict를 받더라도 안전해야 함
# ============================================================

def test_apply_update_raw_dict_skips_missing(fake_model):
    """raw dict에 MISSING이 섞여도 해당 필드는 건드리지 않음"""
    fake_model.apply_update({"name": MISSING, "score": MISSING})

    assert fake_model.name == "original"
    assert fake_model.score == 10


def test_apply_update_raw_dict_mixed_missing(fake_model):
    """raw dict에 MISSING과 실제 값이 섞인 경우 실제 값만 반영"""
    fake_model.apply_update({
        "name": "updated",
        "description": MISSING,
        "score": MISSING,
    })

    assert fake_model.name == "updated"
    assert fake_model.description == "original desc"
    assert fake_model.score == 10


def test_apply_update_raw_dict_missing_vs_none(fake_model):
    """raw dict: MISSING은 스킵, None은 nullable 필드에 적용"""
    fake_model.apply_update({
        "name": MISSING,
        "description": None,
    })

    assert fake_model.name == "original"
    assert fake_model.description is None


def test_apply_update_raw_dict_all_missing(fake_model):
    """raw dict: 모든 값이 MISSING이면 아무것도 변경되지 않음"""
    fake_model.apply_update({
        "name": MISSING,
        "description": MISSING,
        "score": MISSING,
    })

    assert fake_model.name == "original"
    assert fake_model.description == "original desc"
    assert fake_model.score == 10
