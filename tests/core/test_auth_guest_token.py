"""
게스트 토큰 판정 (schema_id 클레임)

회원 인증 진입점(REST get_current_user·get_optional_current_user, GraphQL, WebSocket)은 모두
ensure_member를 거친다. 게스트 schema의 토큰은 403, GUEST_ENABLED인데 schema_id가 없으면 401.
schema_id가 비어 있지 않은 문자열이 아니면 없는 것과 같다.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, WebSocketException
from fastapi.security import HTTPAuthorizationCredentials

import app.core.config as app_config
from app.core.auth import CurrentUser, ensure_member, get_current_user, get_optional_current_user, oidc_client

MEMBER_CLAIMS = {"sub": "member-1", "email": "m@example.com", "email_verified": True, "schema_id": "default"}
GUEST_CLAIMS = {"sub": "guest-1", "name": "민수", "email_verified": False, "schema_id": "guest"}
LEGACY_CLAIMS = {"sub": "member-2", "email": "l@example.com", "email_verified": True}
CREDENTIALS = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")


@pytest.fixture
def guest_flag(monkeypatch):
    def set_flag(enabled: bool):
        monkeypatch.setattr(app_config.settings, "GUEST_ENABLED", enabled)
    return set_flag


def _request(state_user=None):
    request = MagicMock()
    request.state.current_user = state_user
    return request


async def _rest_user(claims: dict):
    with patch("app.core.auth.dependencies.settings") as mock_settings, \
            patch.object(oidc_client, "verify_token", new_callable=AsyncMock, return_value=claims):
        mock_settings.OIDC_ENABLED = True
        return await get_current_user(request=_request(), credentials=CREDENTIALS)


def test_from_claims_reads_schema_id():
    assert CurrentUser.from_claims(GUEST_CLAIMS).schema_id == "guest"
    assert CurrentUser.from_claims(LEGACY_CLAIMS).schema_id is None


NON_TEXT_SCHEMA_IDS = [["guest"], {"id": "guest"}, 0, 1, True, False, ""]


@pytest.mark.parametrize("schema_id", NON_TEXT_SCHEMA_IDS)
def test_non_text_schema_id_reads_as_missing(schema_id):
    user = CurrentUser.from_claims({**MEMBER_CLAIMS, "schema_id": schema_id})
    assert user.schema_id is None
    assert user.is_guest is False


def test_is_guest_follows_configured_schema_id(monkeypatch):
    user = CurrentUser.from_claims({**GUEST_CLAIMS, "schema_id": "visitor"})
    assert user.is_guest is False
    monkeypatch.setattr(app_config.settings, "KRATOS_GUEST_SCHEMA_ID", "visitor")
    assert user.is_guest is True


def test_mock_user_is_not_guest():
    assert CurrentUser.mock().is_guest is False


@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.asyncio
async def test_guest_token_is_forbidden(guest_flag, enabled):
    guest_flag(enabled)
    with pytest.raises(HTTPException) as exc_info:
        await _rest_user(GUEST_CLAIMS)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_missing_schema_id_is_unauthorized_when_guest_enabled(guest_flag):
    guest_flag(True)
    with pytest.raises(HTTPException) as exc_info:
        await _rest_user(LEGACY_CLAIMS)
    assert exc_info.value.status_code == 401
    assert "schema_id" in exc_info.value.detail


@pytest.mark.asyncio
async def test_missing_schema_id_is_accepted_when_guest_disabled(guest_flag):
    guest_flag(False)
    assert (await _rest_user(LEGACY_CLAIMS)).sub == "member-2"


@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.asyncio
async def test_member_token_is_accepted(guest_flag, enabled):
    guest_flag(enabled)
    assert (await _rest_user(MEMBER_CLAIMS)).sub == "member-1"


@pytest.mark.asyncio
async def test_guest_set_by_middleware_is_forbidden(guest_flag):
    """AuthMiddleware가 request.state에 넣어 둔 게스트도 거부한다"""
    guest_flag(True)
    request = _request(CurrentUser.from_claims(GUEST_CLAIMS))
    with patch("app.core.auth.dependencies.settings") as mock_settings:
        mock_settings.OIDC_ENABLED = True
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request=request, credentials=None)
    assert exc_info.value.status_code == 403


@pytest.mark.parametrize("state_user", [None, CurrentUser.from_claims(GUEST_CLAIMS)])
@pytest.mark.asyncio
async def test_optional_user_refuses_guest_instead_of_anonymous(guest_flag, state_user):
    guest_flag(True)
    with patch("app.core.auth.dependencies.settings") as mock_settings, \
            patch.object(oidc_client, "verify_token", new_callable=AsyncMock, return_value=GUEST_CLAIMS):
        mock_settings.OIDC_ENABLED = True
        with pytest.raises(HTTPException) as exc_info:
            await get_optional_current_user(request=_request(state_user), credentials=CREDENTIALS)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_oidc_disabled_mock_user_passes_with_guest_enabled(guest_flag):
    """인증을 끈 개발 환경의 mock 사용자는 schema_id가 없어도 막지 않는다"""
    guest_flag(True)
    with patch("app.core.auth.dependencies.settings") as mock_settings:
        mock_settings.OIDC_ENABLED = False
        user = await get_current_user(request=_request(), credentials=None)
    assert user.sub == CurrentUser.mock().sub


def test_ensure_member_returns_member():
    user = CurrentUser.from_claims(MEMBER_CLAIMS)
    assert ensure_member(user) is user


@pytest.mark.asyncio
async def test_graphql_refuses_guest(guest_flag):
    from app.api.v1.graphql import get_context

    guest_flag(True)
    request = MagicMock()
    request.headers = {"Authorization": "Bearer token"}
    with patch("app.api.v1.graphql.settings") as mock_settings, \
            patch("app.api.v1.graphql.oidc_client") as mock_oidc:
        mock_settings.OIDC_ENABLED = True
        mock_oidc.verify_token = AsyncMock(return_value=GUEST_CLAIMS)
        with pytest.raises(HTTPException) as exc_info:
            await get_context(request, MagicMock())
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_graphql_refuses_token_without_schema_id_when_guest_enabled(guest_flag):
    from app.api.v1.graphql import get_context

    guest_flag(True)
    request = MagicMock()
    request.headers = {"Authorization": "Bearer token"}
    with patch("app.api.v1.graphql.settings") as mock_settings, \
            patch("app.api.v1.graphql.oidc_client") as mock_oidc:
        mock_settings.OIDC_ENABLED = True
        mock_oidc.verify_token = AsyncMock(return_value=LEGACY_CLAIMS)
        with pytest.raises(HTTPException) as exc_info:
            await get_context(request, MagicMock())
    assert exc_info.value.status_code == 401


@pytest.mark.parametrize("claims", [GUEST_CLAIMS, LEGACY_CLAIMS])
@pytest.mark.asyncio
async def test_websocket_refuses_guest_and_missing_schema_id(guest_flag, claims):
    from app.websocket.auth import authenticate_websocket

    guest_flag(True)
    websocket = MagicMock()
    websocket.headers = {"sec-websocket-protocol": "authorization.bearer.token"}
    with patch("app.websocket.auth.settings") as mock_settings, \
            patch("app.websocket.auth.oidc_client") as mock_oidc:
        mock_settings.OIDC_ENABLED = True
        mock_oidc.verify_token = AsyncMock(return_value=claims)
        with pytest.raises(WebSocketException):
            await authenticate_websocket(websocket)


# ============ 문자열이 아닌 schema_id ============

@pytest.mark.parametrize("schema_id", NON_TEXT_SCHEMA_IDS)
@pytest.mark.asyncio
async def test_rest_refuses_non_text_schema_id_when_guest_enabled(guest_flag, schema_id):
    guest_flag(True)
    with pytest.raises(HTTPException) as exc_info:
        await _rest_user({**MEMBER_CLAIMS, "schema_id": schema_id})
    assert exc_info.value.status_code == 401


@pytest.mark.parametrize("schema_id", NON_TEXT_SCHEMA_IDS)
@pytest.mark.asyncio
async def test_rest_accepts_non_text_schema_id_like_missing_when_guest_disabled(guest_flag, schema_id):
    guest_flag(False)
    assert (await _rest_user({**MEMBER_CLAIMS, "schema_id": schema_id})).sub == "member-1"


@pytest.mark.parametrize("schema_id", NON_TEXT_SCHEMA_IDS)
@pytest.mark.asyncio
async def test_graphql_refuses_non_text_schema_id_when_guest_enabled(guest_flag, schema_id):
    from app.api.v1.graphql import get_context

    guest_flag(True)
    request = MagicMock()
    request.headers = {"Authorization": "Bearer token"}
    with patch("app.api.v1.graphql.settings") as mock_settings, \
            patch("app.api.v1.graphql.oidc_client") as mock_oidc:
        mock_settings.OIDC_ENABLED = True
        mock_oidc.verify_token = AsyncMock(return_value={**MEMBER_CLAIMS, "schema_id": schema_id})
        with pytest.raises(HTTPException) as exc_info:
            await get_context(request, MagicMock())
    assert exc_info.value.status_code == 401


@pytest.mark.parametrize("schema_id", NON_TEXT_SCHEMA_IDS)
@pytest.mark.asyncio
async def test_websocket_refuses_non_text_schema_id_when_guest_enabled(guest_flag, schema_id):
    from app.websocket.auth import authenticate_websocket

    guest_flag(True)
    websocket = MagicMock()
    websocket.headers = {"sec-websocket-protocol": "authorization.bearer.token"}
    with patch("app.websocket.auth.settings") as mock_settings, \
            patch("app.websocket.auth.oidc_client") as mock_oidc:
        mock_settings.OIDC_ENABLED = True
        mock_oidc.verify_token = AsyncMock(return_value={**MEMBER_CLAIMS, "schema_id": schema_id})
        with pytest.raises(WebSocketException):
            await authenticate_websocket(websocket)
