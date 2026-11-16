"""
Guest Domain Events

리소스가 게스트에 대해 저장한 것을 정리하거나 표시 이름을 바꾸도록 알린다.
owner_id는 게스트의 Kratos identity id다. 리소스는 resource_type·resource_id로 자기 리소스인지 가린다.
게스트 행은 이미 지워졌을 수 있으므로 필요한 값은 이벤트에 담는다.
"""
from dataclasses import dataclass
from uuid import UUID

from app.models.visibility import ResourceType
from app.shared.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class GuestEvent(DomainEvent):
    """게스트 이벤트 공통 베이스 — event_key에 guest_id 포함"""
    guest_id: UUID
    resource_type: ResourceType
    resource_id: UUID

    def event_key(self) -> tuple:
        return (type(self).__qualname__, str(self.guest_id))


@dataclass(frozen=True, kw_only=True)
class GuestDiscarded(GuestEvent):
    """게스트가 폐기됨 (자기 삭제, 리소스 기간 종료·삭제). 게스트 행은 이미 지워졌다"""


@dataclass(frozen=True, kw_only=True)
class GuestRenamed(GuestEvent):
    """게스트가 이름을 바꿈. Kratos가 바뀐 이름을 저장하기 직전에 발행된다"""
    name: str
