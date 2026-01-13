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
