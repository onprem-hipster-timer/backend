"""
OIDC 인증 패키지

joserfc 기반 OIDC discovery 및 JWT Access Token 검증. 모든 API 엔드포인트를 보호하고
CurrentUser 컨텍스트를 제공한다. 책임별로 분리:

- model:        CurrentUser (인증 주체 모델)
- client:       OIDCClient / oidc_client (discovery·JWKS·토큰 검증)
- dependencies: get_current_user / get_optional_current_user / get_current_user_synced
- middleware:   AuthMiddleware (request.state 사전 설정)

하위호환: 기존 `from app.core.auth import X`가 그대로 동작하도록 공개 심볼을 재export한다.
"""
from app.core.auth.client import OIDCClient, oidc_client
from app.core.auth.dependencies import (
    get_current_user,
    get_current_user_synced,
    get_optional_current_user,
    security,
)
from app.core.auth.middleware import AuthMiddleware
from app.core.auth.model import CurrentUser

__all__ = [
    "CurrentUser",
    "OIDCClient",
    "oidc_client",
    "security",
    "get_current_user",
    "get_optional_current_user",
    "get_current_user_synced",
    "AuthMiddleware",
]
