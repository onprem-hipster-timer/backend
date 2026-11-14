"""
Guest Domain DTO

이름과 비밀번호는 먼저 NFC로 정규화한다. 기기마다 같은 글자가 다른 유니코드 형태로 올 수 있다.
이름은 앞뒤 공백을 떼고 1~50자, 제어 문자는 받지 않는다. 같은 리소스 안에서 이름은 겹치지 않는다
(정규화한 이름이 정확히 같으면 같은 이름).
비밀번호는 비어 있지 않고 UTF-8로 72바이트 이하(bcrypt 한도)면 받는다. 다른 규칙은 없다.
"""
import unicodedata
from uuid import UUID

from pydantic import field_validator

from app.core.base_model import CustomModel
from app.models.visibility import ResourceType

GUEST_NAME_MAX_LENGTH = 50
GUEST_PASSWORD_MAX_BYTES = 72


def normalize_guest_name(value: str) -> str:
    """NFC로 정규화하고 앞뒤 공백을 뗀 이름. 규칙에 맞지 않으면 ValueError"""
    name = unicodedata.normalize("NFC", value).strip()
    if not 1 <= len(name) <= GUEST_NAME_MAX_LENGTH:
        raise ValueError(f"이름은 1~{GUEST_NAME_MAX_LENGTH}자여야 합니다")
    if any(unicodedata.category(ch) == "Cc" for ch in name):
        raise ValueError("이름에 제어 문자를 쓸 수 없습니다")
    return name


class GuestLookup(CustomModel):
    """게스트 이름 찾기 요청"""
    resource_type: ResourceType
    resource_id: UUID
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return normalize_guest_name(v)


class GuestLookupRead(CustomModel):
    """게스트 이름 찾기 응답. 그 이름의 게스트가 없으면 handle은 null"""
    handle: str | None


class GuestCreate(GuestLookup):
    """게스트 생성 요청"""
    password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        v = unicodedata.normalize("NFC", v)
        if not v:
            raise ValueError("비밀번호를 입력하세요")
        if len(v.encode("utf-8")) > GUEST_PASSWORD_MAX_BYTES:
            raise ValueError(f"비밀번호는 {GUEST_PASSWORD_MAX_BYTES}바이트 이하여야 합니다")
        return v


class GuestRead(CustomModel):
    """게스트 생성 응답. 클라이언트는 handle과 비밀번호로 Kratos에 로그인한다"""
    guest_id: UUID
    handle: str
    resource_type: ResourceType
    resource_id: UUID
