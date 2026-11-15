"""
계정 접근 기록 (app/core/audit.py)

- 전용 로거가 stdout으로 순수 JSON 한 줄을 쓴다 (다른 접두사 없음)
- 키는 audit, event, identity_id, ip, at뿐이다
"""
import io
import json
import logging
from datetime import datetime, timedelta

import pytest

from app.core import audit


@pytest.fixture
def output(monkeypatch):
    stream = io.StringIO()
    monkeypatch.setattr(audit._handler, "stream", stream)
    # alembic env.py의 fileConfig가 같은 프로세스의 기존 로거를 끈다 (마이그레이션 테스트)
    monkeypatch.setattr(audit._logger, "disabled", False)
    return stream


def test_handler_writes_to_stdout_without_propagating():
    assert audit._logger.name == audit.AUDIT_LOGGER_NAME
    assert audit._logger.propagate is False
    assert audit._logger.level == logging.INFO
    assert audit._handler in audit._logger.handlers
    record = logging.LogRecord(audit.AUDIT_LOGGER_NAME, logging.INFO, "", 0, '{"a": 1}', None, None)
    assert audit._handler.format(record) == '{"a": 1}'


def test_line_is_pure_json_with_exact_keys(output):
    audit.log_account_access("login", "identity-1", "203.0.113.7")

    lines = output.getvalue().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert list(record) == ["audit", "event", "identity_id", "ip", "at"]
    assert record["audit"] == "account_access"
    assert record["event"] == "login"
    assert record["identity_id"] == "identity-1"
    assert record["ip"] == "203.0.113.7"
    at = datetime.fromisoformat(record["at"])
    assert at.utcoffset() == timedelta(0)


def test_missing_ip_is_null(output):
    audit.log_account_access("account_purged", "identity-1", None)

    assert json.loads(output.getvalue())["ip"] is None


def test_unknown_event_is_rejected(output):
    with pytest.raises(ValueError):
        audit.log_account_access("logout", "identity-1", None)
    assert output.getvalue() == ""
