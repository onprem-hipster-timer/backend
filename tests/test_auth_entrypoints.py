"""
GraphQL·WebSocket 인증 진입점의 클레임 매핑 테스트

REST와 같은 CurrentUser.from_claims를 써서 email_verified 등 클레임이 빠지지 않는지 확인한다.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

CLAIMS = {
    "sub": "9f1c3a52-6a0e-4c2b-9d3f-1b2c3d4e5f60",
    "email": "kratos@example.com",
    "email_verified": True,
    "name": "Kratos User",
}


@pytest.mark.asyncio
async def test_websocket_auth_keeps_email_verified():
    from app.websocket.auth import authenticate_websocket

    websocket = MagicMock()
    websocket.headers = {"sec-websocket-protocol": "authorization.bearer.token"}
    with patch("app.websocket.auth.settings") as mock_settings, \
            patch("app.websocket.auth.oidc_client") as mock_oidc:
        mock_settings.OIDC_ENABLED = True
        mock_oidc.verify_token = AsyncMock(return_value=CLAIMS)

        user = await authenticate_websocket(websocket)

    assert user.sub == CLAIMS["sub"]
    assert user.email_verified is True


@pytest.mark.asyncio
async def test_graphql_context_keeps_email_verified():
    from app.api.v1.graphql import get_context

    request = MagicMock()
    request.headers = {"Authorization": "Bearer token"}
    with patch("app.api.v1.graphql.settings") as mock_settings, \
            patch("app.api.v1.graphql.oidc_client") as mock_oidc, \
            patch("app.api.v1.graphql.get_db", return_value=iter([MagicMock()])):
        mock_settings.OIDC_ENABLED = True
        mock_oidc.verify_token = AsyncMock(return_value=CLAIMS)

        context = await get_context(request)

    assert context["current_user"].sub == CLAIMS["sub"]
    assert context["current_user"].email_verified is True
