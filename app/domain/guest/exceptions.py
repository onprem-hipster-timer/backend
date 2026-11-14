"""
Guest Domain Exceptions
"""
from fastapi import status

from app.core.error_handlers import DomainException


class GuestEntryRefusedError(DomainException):
    """리소스에 게스트로 들어갈 수 없음 (리소스가 없거나 게스트를 받지 않음)"""
    status_code = status.HTTP_403_FORBIDDEN
    detail = "게스트로 들어갈 수 없습니다"


class GuestNameTakenError(DomainException):
    """같은 리소스에 같은 이름의 게스트가 이미 있음"""
    status_code = status.HTTP_409_CONFLICT
    detail = "같은 이름의 게스트가 이미 있습니다. 다른 이름을 쓰세요"


class GuestLimitReachedError(DomainException):
    """리소스의 게스트 수가 상한에 닿음"""
    status_code = status.HTTP_409_CONFLICT
    detail = "이 리소스에는 게스트를 더 만들 수 없습니다"


class GuestAccessDeniedError(DomainException):
    """게스트 토큰이 이 리소스에 접근할 수 없음"""
    status_code = status.HTTP_403_FORBIDDEN
    detail = "게스트로 접근할 수 없습니다"


class GuestServiceUnavailableError(DomainException):
    """Kratos에 닿지 않아 게스트 처리를 마치지 못함"""
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    detail = "인증 서비스에 연결할 수 없습니다"


class GuestVerificationFailedError(DomainException):
    """게스트 생성 요청의 Turnstile 토큰이 확인을 통과하지 못함"""
    status_code = status.HTTP_403_FORBIDDEN
    detail = "확인을 통과하지 못했습니다. 다시 시도하세요"
