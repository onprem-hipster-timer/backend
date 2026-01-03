"""
Validators Tests
"""
import pytest

from app.utils.validators import validate_color, validate_time_order
from datetime import datetime, UTC


# ============================================================
# validate_time_order Tests
# ============================================================

def test_validate_time_order_success():
    """시간 순서 검증 성공"""
    start_time = datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC)
    end_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    
    # 예외가 발생하지 않아야 함
    validate_time_order(start_time, end_time)


def test_validate_time_order_failure():
    """시간 순서 검증 실패 (end_time <= start_time)"""
    start_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    end_time = datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC)
    
    with pytest.raises(ValueError, match="end_time must be after start_time"):
        validate_time_order(start_time, end_time)


# ============================================================
# validate_color Tests
# ============================================================

def test_validate_color_success_short():
    """색상 검증 성공 (짧은 형식)"""
    color = "#FFF"
    result = validate_color(color)
    assert result == "#FFF"


def test_validate_color_success_long():
    """색상 검증 성공 (긴 형식)"""
    color = "#FFFFFF"
    result = validate_color(color)
    assert result == "#FFFFFF"


def test_validate_color_uppercase():
    """색상 대문자 변환"""
    color = "#ff5733"
    result = validate_color(color)
    assert result == "#FF5733"


def test_validate_color_none():
    """색상 None 처리"""
    result = validate_color(None)
    assert result is None


def test_validate_color_missing_hash():
    """색상 검증 실패 (# 없음)"""
    with pytest.raises(ValueError, match="색상은 HEX 형식이어야 합니다"):
        validate_color("FF5733")


def test_validate_color_invalid_length():
    """색상 검증 실패 (잘못된 길이)"""
    with pytest.raises(ValueError, match="색상은 HEX 형식이어야 합니다"):
        validate_color("#FF")  # 너무 짧음
    
    with pytest.raises(ValueError, match="색상은 HEX 형식이어야 합니다"):
        validate_color("#FFFFFFF")  # 너무 김


def test_validate_color_empty():
    """색상 검증 실패 (빈 문자열)"""
    with pytest.raises(ValueError, match="색상은 HEX 형식이어야 합니다"):
        validate_color("")


def test_validate_color_only_hash():
    """색상 검증 실패 (#만 있음)"""
    with pytest.raises(ValueError, match="색상은 HEX 형식이어야 합니다"):
        validate_color("#")

