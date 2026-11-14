"""
게스트 호스트 계약

게스트를 받는 리소스(호스트)는 리소스 종류마다 GuestHost 구현을 register_guest_host로 등록한다.
의존 방향은 리소스 → 게스트다. 이 도메인은 리소스 도메인을 import하지 않는다.
등록되지 않은 리소스 종류는 MISSING으로 본다.

테스트: tests/domain/guest/test_policy.py
"""
from enum import Enum
from typing import Protocol
from uuid import UUID

from sqlmodel import Session

from app.models.visibility import ResourceType


class GuestHostStatus(str, Enum):
    """리소스가 지금 게스트를 받는지"""
    OPEN = "open"  # 있고, 게스트를 받으며, 게스트 기간 안이다
    CLOSED = "closed"  # 있지만 지금은 게스트를 받지 않는다 (게스트는 남는다)
    EXPIRED = "expired"  # 게스트 기간이 끝났다 (게스트를 폐기한다)
    MISSING = "missing"  # 없다 (게스트를 폐기한다)


class GuestHost(Protocol):
    """리소스가 구현할 계약"""

    def guest_status(self, session: Session, resource_id: UUID) -> GuestHostStatus:
        """resource_id 리소스가 지금 게스트를 받는지. 읽기만 하고 세션을 커밋하지 않는다."""
        ...


_hosts: dict[ResourceType, GuestHost] = {}


def register_guest_host(resource_type: ResourceType, host: GuestHost) -> None:
    """리소스 종류의 호스트를 등록한다. 다시 등록하면 바꾼다."""
    _hosts[resource_type] = host


def unregister_guest_host(resource_type: ResourceType) -> None:
    _hosts.pop(resource_type, None)


def host_status(session: Session, resource_type: ResourceType, resource_id: UUID) -> GuestHostStatus:
    host = _hosts.get(resource_type)
    if host is None:
        return GuestHostStatus.MISSING
    return host.guest_status(session, resource_id)
