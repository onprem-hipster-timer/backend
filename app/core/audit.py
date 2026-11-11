"""
계정 접근 기록

로그인·가입·탈퇴 신청·취소·파기를 stdout에 JSON 한 줄로 남긴다. 다른 로그와 섞이지 않게
전용 로거가 메시지만 쓰므로 Cloud Logging이 jsonPayload로 읽는다. 보존 기간은 infra가 정한다.

형식: {"audit": "account_access", "event": ..., "identity_id": ..., "ip": ..., "at": UTC ISO 8601}
테스트: tests/core/test_audit.py
"""
import json
import logging
import sys
from datetime import UTC, datetime

AUDIT_LOGGER_NAME = "app.audit.account_access"
EVENTS = frozenset({"login", "registration", "deletion_requested", "deletion_cancelled", "account_purged"})

_logger = logging.getLogger(AUDIT_LOGGER_NAME)
_logger.setLevel(logging.INFO)
_logger.propagate = False
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(logging.Formatter("%(message)s"))
_logger.addHandler(_handler)


def log_account_access(event: str, identity_id: str, ip: str | None) -> None:
    """접근 기록 한 줄. 이메일 등 다른 값은 넣지 않는다."""
    if event not in EVENTS:
        raise ValueError(f"unknown account access event: {event}")
    _logger.info(json.dumps({
        "audit": "account_access",
        "event": event,
        "identity_id": identity_id,
        "ip": ip,
        "at": datetime.now(UTC).isoformat(),
    }))
