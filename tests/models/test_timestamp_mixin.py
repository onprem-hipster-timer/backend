"""
TimestampMixin & utc_now_naive Tests
"""
from datetime import datetime

from app.models.base import utc_now_naive
from tests.models.conftest import FakeModel


# ============================================================
# utc_now_naive
# ============================================================

def test_utc_now_naive_returns_naive_datetime():
    """timezone 정보 없는 datetime 반환"""
    result = utc_now_naive()

    assert result.tzinfo is None


def test_utc_now_naive_returns_current_utc():
    """현재 UTC 시간 반환"""
    before = utc_now_naive()
    result = utc_now_naive()
    after = utc_now_naive()

    assert before <= result <= after


# ============================================================
# TimestampMixin
# ============================================================

def test_timestamp_created_at_auto_set():
    """생성 시 created_at 자동 설정"""
    before = utc_now_naive()
    entity = FakeModel()
    after = utc_now_naive()

    assert before <= entity.created_at <= after


def test_timestamp_updated_at_auto_set():
    """생성 시 updated_at 자동 설정"""
    before = utc_now_naive()
    entity = FakeModel()
    after = utc_now_naive()

    assert before <= entity.updated_at <= after


def test_timestamps_are_naive():
    """타임스탬프에 timezone 정보 없음"""
    entity = FakeModel()

    assert entity.created_at.tzinfo is None
    assert entity.updated_at.tzinfo is None


def test_timestamps_created_at_and_updated_at_close():
    """created_at과 updated_at이 거의 동일한 시간"""
    entity = FakeModel()

    diff = abs((entity.updated_at - entity.created_at).total_seconds())
    assert diff < 1


def test_timestamps_accept_explicit_values():
    """명시적 타임스탬프 주입 허용"""
    ts = datetime(2025, 1, 1, 12, 0, 0)
    entity = FakeModel(created_at=ts, updated_at=ts)

    assert entity.created_at == ts
    assert entity.updated_at == ts
