"""
Domain Event 기반 타입

이벤트는 발생한 도메인 사실만 담는 불변 값 객체다. payload에는 식별자와
도메인 사실만 담는다 (API DTO/ORM 인스턴스 금지, datetime은 naive-UTC,
컬렉션은 tuple — frozen 유지).
"""
from dataclasses import dataclass
from enum import Enum


class EventOrigin(str, Enum):
    """이벤트를 촉발한 source 도메인 (왕복 전파 차단용)"""
    TODO = "todo"
    SCHEDULE = "schedule"


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    """
    모든 도메인 이벤트의 베이스

    :param owner_id: 리소스 소유자 (OIDC sub). 핸들러는 변경 대상의
        owner_id가 이와 일치할 때만 수정한다.
    :param origin: 이벤트를 촉발한 source 도메인
    """
    owner_id: str
    origin: EventOrigin

    def event_key(self) -> tuple:
        """
        중복 dispatch 억제 키 — 타입 + 주요 식별자

        같은 drain 루프 안에서 동일 키의 이벤트는 한 번만 처리된다.
        서브클래스는 주요 식별자를 포함하도록 재정의한다.
        """
        return (type(self).__qualname__, self.owner_id)
