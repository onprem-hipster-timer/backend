"""
Rate Limit 예외 정의
"""
from app.core.error_handlers import DomainException


class RateLimitExceededError(DomainException):
    """레이트 리밋 초과 예외"""
    status_code: int = 429
    detail: str = "요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요."

    def __init__(self, retry_after: int = 60):
        self.retry_after = retry_after
        super().__init__()


class ProxyEnforcementError(DomainException):
    """프록시(또는 Cloudflare) 경유가 강제된 환경에서 직접 접근이 감지된 경우"""

    status_code: int = 403
    detail: str = "프록시를 통하지 않은 접근은 허용되지 않습니다."
