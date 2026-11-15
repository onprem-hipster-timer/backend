"""
게스트 토큰 판정 (schema_id 클레임)

회원 인증 진입점(REST get_current_user·get_optional_current_user, GraphQL, WebSocket)은 모두
ensure_member를 거친다. GUEST_ENABLED와 상관없이 게스트 schema의 토큰은 403, schema_id가 없으면 401.
schema_id가 비어 있지 않은 문자열이 아니면 없는 것과 같다. OIDC_ENABLED=false의 mock 사용자는 그대로 통과한다.
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


# 클레임이 없는 토큰과 비어 있지 않은 문자열이 아닌 schema_id
UNUSABLE_CLAIMS = [LEGACY_CLAIMS] + [{**MEMBER_CLAIMS, "schema_id": value} for value in NON_TEXT_SCHEMA_IDS]
UNUSABLE_IDS = ["missing", "list", "object", "zero", "one", "true", "false", "empty"]
FLAGS = pytest.mark.parametrize("enabled", [True, False], ids=["guest_on", "guest_off"])


@FLAGS
@pytest.mark.parametrize("claims", UNUSABLE_CLAIMS, ids=UNUSABLE_IDS)
@pytest.mark.asyncio
async def test_rest_refuses_token_without_usable_schema_id(guest_flag, enabled, claims):
    guest_flag(enabled)
    with pytest.raises(HTTPException) as exc_info:
        await _rest_user(claims)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Token missing 'schema_id' claim"


@FLAGS
@pytest.mark.parametrize("claims", UNUSABLE_CLAIMS, ids=UNUSABLE_IDS)
@pytest.mark.asyncio
async def test_optional_user_refuses_token_without_usable_schema_id(guest_flag, enabled, claims):
    guest_flag(enabled)
    with patch("app.core.auth.dependencies.settings") as mock_settings, \
            patch.object(oidc_client, "verify_token", new_callable=AsyncMock, return_value=claims):
        mock_settings.OIDC_ENABLED = True
        with pytest.raises(HTTPException) as exc_info:
            await get_optional_current_user(request=_request(), credentials=CREDENTIALS)
    assert exc_info.value.status_code == 401


@FLAGS
@pytest.mark.parametrize("schema_id", ["default", "member", "Guest", "guest "])
@pytest.mark.asyncio
async def test_other_schema_id_is_member(guest_flag, enabled, schema_id):
    guest_flag(enabled)
    assert (await _rest_user({**MEMBER_CLAIMS, "schema_id": schema_id})).sub == "member-1"


@FLAGS
@pytest.mark.asyncio
async def test_guest_token_is_forbidden_on_rest(guest_flag, enabled):
    guest_flag(enabled)
    with pytest.raises(HTTPException) as exc_info:
        await _rest_user(GUEST_CLAIMS)
    assert exc_info.value.status_code == 403


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


@FLAGS
@pytest.mark.asyncio
async def test_oidc_disabled_mock_user_passes(guest_flag, enabled):
    """인증을 끈 개발 환경의 mock 사용자는 schema_id가 없어도 막지 않는다"""
    guest_flag(enabled)
    with patch("app.core.auth.dependencies.settings") as mock_settings:
        mock_settings.OIDC_ENABLED = False
        user = await get_current_user(request=_request(), credentials=None)
        optional = await get_optional_current_user(request=_request(), credentials=None)
    assert user.sub == optional.sub == CurrentUser.mock().sub


def test_ensure_member_returns_member():
    user = CurrentUser.from_claims(MEMBER_CLAIMS)
    assert ensure_member(user) is user


# ============ GraphQL, WebSocket ============

async def _graphql_context(claims: dict | None, oidc_enabled: bool = True):
    from app.api.v1.graphql import get_context
    from app.domain.user.service import AccountState

    request = MagicMock()
    request.headers = {"Authorization": "Bearer token"}
    with patch("app.api.v1.graphql.settings") as mock_settings, \
            patch("app.api.v1.graphql.oidc_client") as mock_oidc, \
            patch("app.domain.user.service.account_state", return_value=AccountState.ACTIVE):
        mock_settings.OIDC_ENABLED = oidc_enabled
        mock_oidc.verify_token = AsyncMock(return_value=claims)
        return await get_context(request, MagicMock())


async def _websocket_user(claims: dict | None, oidc_enabled: bool = True):
    from app.websocket.auth import authenticate_websocket

    websocket = MagicMock()
    websocket.headers = {"sec-websocket-protocol": "authorization.bearer.token"}
    with patch("app.websocket.auth.settings") as mock_settings, \
            patch("app.websocket.auth.oidc_client") as mock_oidc:
        mock_settings.OIDC_ENABLED = oidc_enabled
        mock_oidc.verify_token = AsyncMock(return_value=claims)
        return await authenticate_websocket(websocket)


@FLAGS
@pytest.mark.parametrize("claims", UNUSABLE_CLAIMS, ids=UNUSABLE_IDS)
@pytest.mark.asyncio
async def test_graphql_refuses_token_without_usable_schema_id(guest_flag, enabled, claims):
    guest_flag(enabled)
    with pytest.raises(HTTPException) as exc_info:
        await _graphql_context(claims)
    assert exc_info.value.status_code == 401


@FLAGS
@pytest.mark.asyncio
async def test_graphql_refuses_guest(guest_flag, enabled):
    guest_flag(enabled)
    with pytest.raises(HTTPException) as exc_info:
        await _graphql_context(GUEST_CLAIMS)
    assert exc_info.value.status_code == 403


@FLAGS
@pytest.mark.asyncio
async def test_graphql_accepts_member(guest_flag, enabled):
    guest_flag(enabled)
    assert (await _graphql_context(MEMBER_CLAIMS))["current_user"].sub == "member-1"


@FLAGS
@pytest.mark.asyncio
async def test_graphql_oidc_disabled_mock_user_passes(guest_flag, enabled):
    guest_flag(enabled)
    assert (await _graphql_context(None, oidc_enabled=False))["current_user"].sub == CurrentUser.mock().sub


@FLAGS
@pytest.mark.parametrize("claims", UNUSABLE_CLAIMS + [GUEST_CLAIMS], ids=UNUSABLE_IDS + ["guest"])
@pytest.mark.asyncio
async def test_websocket_refuses_guest_and_token_without_usable_schema_id(guest_flag, enabled, claims):
    guest_flag(enabled)
    with pytest.raises(WebSocketException) as exc_info:
        await _websocket_user(claims)
    assert exc_info.value.code == 1008


@FLAGS
@pytest.mark.asyncio
async def test_websocket_accepts_member(guest_flag, enabled):
    guest_flag(enabled)
    assert (await _websocket_user(MEMBER_CLAIMS)).sub == "member-1"


@FLAGS
@pytest.mark.asyncio
async def test_websocket_oidc_disabled_mock_user_passes(guest_flag, enabled):
    guest_flag(enabled)
    assert (await _websocket_user(None, oidc_enabled=False)).sub == CurrentUser.mock().sub
