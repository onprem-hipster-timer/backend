"""
OIDC 인증 모듈 테스트

OIDCClient, CurrentUser, get_current_user dependency 테스트
"""
import time
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from authlib.jose import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials


# ============================================================================
# 테스트용 RSA 키 동적 생성
# ============================================================================

def generate_rsa_keypair():
    """테스트용 RSA 키 쌍 동적 생성"""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    # JWKS 형태로 공개키 변환
    from authlib.jose import JsonWebKey
    jwk = JsonWebKey.import_key(public_pem, {"kty": "RSA", "use": "sig", "kid": "test-key-id"})
    jwks = {"keys": [jwk.as_dict()]}

    return private_pem, public_pem, jwks


# 테스트 시작 시 한 번만 생성
TEST_PRIVATE_KEY, TEST_PUBLIC_KEY, TEST_JWKS = generate_rsa_keypair()


def create_test_token(
        sub: str = "test-user-123",
        email: str = "test@example.com",
        name: str = "Test User",
        iss: str = "https://test-issuer.example.com",
        aud: str | list = "test-client-id",
        exp_delta: timedelta = timedelta(hours=1),
        extra_claims: dict = None,
) -> str:
    """테스트용 JWT 토큰 생성"""
    now = int(time.time())
    exp = now + int(exp_delta.total_seconds())

    claims = {
        "sub": sub,
        "email": email,
        "name": name,
        "iss": iss,
        "aud": aud,
        "iat": now,
        "exp": exp,
    }

    if extra_claims:
        claims.update(extra_claims)

    header = {"alg": "RS256", "kid": "test-key-id"}
    token = jwt.encode(header, claims, TEST_PRIVATE_KEY)
    return token.decode() if isinstance(token, bytes) else token


# ============================================================================
# CurrentUser 모델 테스트
# ============================================================================

class TestCurrentUser:
    """CurrentUser 모델 테스트"""

    def test_create_current_user_minimal(self):
        """최소 필수 필드로 CurrentUser 생성"""
        from app.core.auth import CurrentUser

        user = CurrentUser(sub="user-123")

        assert user.sub == "user-123"
        assert user.email is None
        assert user.name is None
        assert user.raw_claims == {}

    def test_create_current_user_full(self):
        """모든 필드로 CurrentUser 생성"""
        from app.core.auth import CurrentUser

        user = CurrentUser(
            sub="user-123",
            email="test@example.com",
            name="Test User",
            raw_claims={"custom": "claim"},
        )

        assert user.sub == "user-123"
        assert user.email == "test@example.com"
        assert user.name == "Test User"
        assert user.raw_claims == {"custom": "claim"}


# ============================================================================
# OIDCClient 테스트
# ============================================================================

class TestOIDCClient:
    """OIDCClient 클래스 테스트"""

    def test_discovery_url_default(self):
        """OIDC discovery URL 기본 생성"""
        from app.core.auth import OIDCClient

        with patch("app.core.auth.settings") as mock_settings:
            mock_settings.OIDC_ISSUER_URL = "https://issuer.example.com"
            mock_settings.OIDC_DISCOVERY_URL = None
            mock_settings.OIDC_JWKS_CACHE_TTL_SECONDS = 3600

            client = OIDCClient()

            assert client.discovery_url == "https://issuer.example.com/.well-known/openid-configuration"

    def test_discovery_url_custom(self):
        """커스텀 discovery URL 사용"""
        from app.core.auth import OIDCClient

        with patch("app.core.auth.settings") as mock_settings:
            mock_settings.OIDC_ISSUER_URL = "https://issuer.example.com"
            mock_settings.OIDC_DISCOVERY_URL = "https://custom.example.com/oidc/.well-known/openid-configuration"
            mock_settings.OIDC_JWKS_CACHE_TTL_SECONDS = 3600

            client = OIDCClient()

            assert client.discovery_url == "https://custom.example.com/oidc/.well-known/openid-configuration"

    def test_discovery_url_trailing_slash(self):
        """issuer URL 끝에 슬래시가 있어도 올바르게 처리"""
        from app.core.auth import OIDCClient

        with patch("app.core.auth.settings") as mock_settings:
            mock_settings.OIDC_ISSUER_URL = "https://issuer.example.com/"
            mock_settings.OIDC_DISCOVERY_URL = None
            mock_settings.OIDC_JWKS_CACHE_TTL_SECONDS = 3600

            client = OIDCClient()

            assert client.discovery_url == "https://issuer.example.com/.well-known/openid-configuration"

    @pytest.mark.asyncio
    async def test_get_metadata_success(self):
        """OIDC metadata 조회 성공"""
        from app.core.auth import OIDCClient

        mock_metadata = {
            "issuer": "https://issuer.example.com",
            "jwks_uri": "https://issuer.example.com/.well-known/jwks.json",
            "authorization_endpoint": "https://issuer.example.com/authorize",
            "token_endpoint": "https://issuer.example.com/token",
        }

        with patch("app.core.auth.settings") as mock_settings:
            mock_settings.OIDC_ISSUER_URL = "https://issuer.example.com"
            mock_settings.OIDC_DISCOVERY_URL = None
            mock_settings.OIDC_JWKS_CACHE_TTL_SECONDS = 3600

            client = OIDCClient()

            with patch("httpx.AsyncClient") as mock_client_class:
                mock_response = MagicMock()
                mock_response.json.return_value = mock_metadata
                mock_response.raise_for_status = MagicMock()

                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client_class.return_value = mock_client

                metadata = await client.get_metadata()

                assert metadata == mock_metadata
                assert metadata["issuer"] == "https://issuer.example.com"

    @pytest.mark.asyncio
    async def test_get_metadata_cached(self):
        """OIDC metadata 캐싱 확인"""
        from app.core.auth import OIDCClient

        mock_metadata = {
            "issuer": "https://issuer.example.com",
            "jwks_uri": "https://issuer.example.com/.well-known/jwks.json",
        }

        with patch("app.core.auth.settings") as mock_settings:
            mock_settings.OIDC_ISSUER_URL = "https://issuer.example.com"
            mock_settings.OIDC_DISCOVERY_URL = None
            mock_settings.OIDC_JWKS_CACHE_TTL_SECONDS = 3600

            client = OIDCClient()

            with patch("httpx.AsyncClient") as mock_client_class:
                mock_response = MagicMock()
                mock_response.json.return_value = mock_metadata
                mock_response.raise_for_status = MagicMock()

                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client_class.return_value = mock_client

                # 첫 번째 호출 - HTTP 요청
                metadata1 = await client.get_metadata()
                # 두 번째 호출 - 캐시에서
                metadata2 = await client.get_metadata()

                # HTTP 요청은 한 번만 발생해야 함
                assert mock_client.get.call_count == 1
                assert metadata1 == metadata2

    @pytest.mark.asyncio
    async def test_get_jwks_success(self):
        """JWKS 조회 성공"""
        from app.core.auth import OIDCClient

        mock_metadata = {
            "issuer": "https://issuer.example.com",
            "jwks_uri": "https://issuer.example.com/.well-known/jwks.json",
        }

        with patch("app.core.auth.settings") as mock_settings:
            mock_settings.OIDC_ISSUER_URL = "https://issuer.example.com"
            mock_settings.OIDC_DISCOVERY_URL = None
            mock_settings.OIDC_JWKS_CACHE_TTL_SECONDS = 3600

            client = OIDCClient()

            with patch("httpx.AsyncClient") as mock_client_class:
                # 첫 번째 호출: metadata, 두 번째 호출: JWKS
                mock_metadata_response = MagicMock()
                mock_metadata_response.json.return_value = mock_metadata
                mock_metadata_response.raise_for_status = MagicMock()

                mock_jwks_response = MagicMock()
                mock_jwks_response.json.return_value = TEST_JWKS
                mock_jwks_response.raise_for_status = MagicMock()

                mock_client = AsyncMock()
                mock_client.get = AsyncMock(side_effect=[mock_metadata_response, mock_jwks_response])
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client_class.return_value = mock_client

                jwks = await client.get_jwks()

                # JsonWebKey 객체가 반환되어야 함
                assert jwks is not None

    @pytest.mark.asyncio
    async def test_get_jwks_no_jwks_uri(self):
        """metadata에 jwks_uri가 없는 경우"""
        from app.core.auth import OIDCClient

        mock_metadata = {
            "issuer": "https://issuer.example.com",
            # jwks_uri 누락
        }

        with patch("app.core.auth.settings") as mock_settings:
            mock_settings.OIDC_ISSUER_URL = "https://issuer.example.com"
            mock_settings.OIDC_DISCOVERY_URL = None
            mock_settings.OIDC_JWKS_CACHE_TTL_SECONDS = 3600

            client = OIDCClient()

            with patch("httpx.AsyncClient") as mock_client_class:
                mock_response = MagicMock()
                mock_response.json.return_value = mock_metadata
                mock_response.raise_for_status = MagicMock()

                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client_class.return_value = mock_client

                with pytest.raises(ValueError, match="jwks_uri"):
                    await client.get_jwks()

    @pytest.mark.asyncio
    async def test_verify_token_valid(self):
        """유효한 토큰 검증 성공"""
        from app.core.auth import OIDCClient
        from authlib.jose import JsonWebKey

        # 유효한 토큰 생성
        token = create_test_token(
            iss="https://issuer.example.com",
            aud="test-client-id",
        )

        with patch("app.core.auth.settings") as mock_settings:
            mock_settings.OIDC_ISSUER_URL = "https://issuer.example.com"
            mock_settings.OIDC_DISCOVERY_URL = None
            mock_settings.OIDC_JWKS_CACHE_TTL_SECONDS = 3600
            mock_settings.OIDC_AUDIENCE = "test-client-id"

            client = OIDCClient()

            # get_jwks를 mock하여 테스트용 JWKS 반환
            jwks = JsonWebKey.import_key_set(TEST_JWKS)
            with patch.object(client, "get_jwks", new_callable=AsyncMock) as mock_get_jwks:
                mock_get_jwks.return_value = jwks

                claims = await client.verify_token(token)

                assert claims["sub"] == "test-user-123"
                assert claims["email"] == "test@example.com"
                assert claims["iss"] == "https://issuer.example.com"

    @pytest.mark.asyncio
    async def test_verify_token_invalid_issuer(self):
        """잘못된 issuer의 토큰 검증 실패"""
        from app.core.auth import OIDCClient
        from authlib.jose import JsonWebKey

        # 잘못된 issuer로 토큰 생성
        token = create_test_token(
            iss="https://wrong-issuer.example.com",
            aud="test-client-id",
        )

        with patch("app.core.auth.settings") as mock_settings:
            mock_settings.OIDC_ISSUER_URL = "https://issuer.example.com"
            mock_settings.OIDC_DISCOVERY_URL = None
            mock_settings.OIDC_JWKS_CACHE_TTL_SECONDS = 3600
            mock_settings.OIDC_AUDIENCE = "test-client-id"

            client = OIDCClient()

            jwks = JsonWebKey.import_key_set(TEST_JWKS)
            with patch.object(client, "get_jwks", new_callable=AsyncMock) as mock_get_jwks:
                mock_get_jwks.return_value = jwks

                with pytest.raises(HTTPException) as exc_info:
                    await client.verify_token(token)

                assert exc_info.value.status_code == 401
                assert "issuer" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_verify_token_invalid_audience(self):
        """잘못된 audience의 토큰 검증 실패"""
        from app.core.auth import OIDCClient
        from authlib.jose import JsonWebKey

        # 잘못된 audience로 토큰 생성
        token = create_test_token(
            iss="https://issuer.example.com",
            aud="wrong-client-id",
        )

        with patch("app.core.auth.settings") as mock_settings:
            mock_settings.OIDC_ISSUER_URL = "https://issuer.example.com"
            mock_settings.OIDC_DISCOVERY_URL = None
            mock_settings.OIDC_JWKS_CACHE_TTL_SECONDS = 3600
            mock_settings.OIDC_AUDIENCE = "correct-client-id"

            client = OIDCClient()

            jwks = JsonWebKey.import_key_set(TEST_JWKS)
            with patch.object(client, "get_jwks", new_callable=AsyncMock) as mock_get_jwks:
                mock_get_jwks.return_value = jwks

                with pytest.raises(HTTPException) as exc_info:
                    await client.verify_token(token)

                assert exc_info.value.status_code == 401
                assert "audience" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_verify_token_expired(self):
        """만료된 토큰 검증 실패"""
        from app.core.auth import OIDCClient
        from authlib.jose import JsonWebKey

        # 만료된 토큰 생성
        token = create_test_token(
            iss="https://issuer.example.com",
            aud="test-client-id",
            exp_delta=timedelta(hours=-1),  # 1시간 전에 만료
        )

        with patch("app.core.auth.settings") as mock_settings:
            mock_settings.OIDC_ISSUER_URL = "https://issuer.example.com"
            mock_settings.OIDC_DISCOVERY_URL = None
            mock_settings.OIDC_JWKS_CACHE_TTL_SECONDS = 3600
            mock_settings.OIDC_AUDIENCE = "test-client-id"

            client = OIDCClient()

            jwks = JsonWebKey.import_key_set(TEST_JWKS)
            with patch.object(client, "get_jwks", new_callable=AsyncMock) as mock_get_jwks:
                mock_get_jwks.return_value = jwks

                with pytest.raises(HTTPException) as exc_info:
                    await client.verify_token(token)

                assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_verify_token_http_error(self):
        """JWKS 조회 실패 시 503 반환"""
        from app.core.auth import OIDCClient

        with patch("app.core.auth.settings") as mock_settings:
            mock_settings.OIDC_ISSUER_URL = "https://issuer.example.com"
            mock_settings.OIDC_DISCOVERY_URL = None
            mock_settings.OIDC_JWKS_CACHE_TTL_SECONDS = 3600

            client = OIDCClient()

            with patch.object(client, "get_jwks", new_callable=AsyncMock) as mock_get_jwks:
                mock_get_jwks.side_effect = httpx.HTTPError("Connection failed")

                with pytest.raises(HTTPException) as exc_info:
                    await client.verify_token("some-token")

                assert exc_info.value.status_code == 503
                assert "unavailable" in exc_info.value.detail.lower()


# ============================================================================
# get_current_user 테스트
# ============================================================================

class TestGetCurrentUser:
    """get_current_user dependency 테스트"""

    @pytest.mark.asyncio
    async def test_oidc_disabled_returns_mock_user(self):
        """OIDC 비활성화 시 mock 사용자 반환"""
        from app.core.auth import get_current_user

        mock_request = MagicMock()
        mock_request.state.current_user = None

        with patch("app.core.auth.settings") as mock_settings:
            mock_settings.OIDC_ENABLED = False

            user = await get_current_user(request=mock_request, credentials=None)

            assert user.sub == "test-user-id"
            assert user.email == "test@example.com"
            assert user.name == "Test User"

    @pytest.mark.asyncio
    async def test_oidc_enabled_no_credentials(self):
        """OIDC 활성화 상태에서 credentials 없으면 401"""
        from app.core.auth import get_current_user

        mock_request = MagicMock()
        mock_request.state.current_user = None

        with patch("app.core.auth.settings") as mock_settings:
            mock_settings.OIDC_ENABLED = True

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(request=mock_request, credentials=None)

            assert exc_info.value.status_code == 401
            assert "Authorization" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_oidc_enabled_missing_sub_claim(self):
        """sub 클레임이 없는 토큰"""
        from app.core.auth import get_current_user, oidc_client

        mock_request = MagicMock()
        mock_request.state.current_user = None

        with patch("app.core.auth.settings") as mock_settings:
            mock_settings.OIDC_ENABLED = True

            credentials = HTTPAuthorizationCredentials(
                scheme="Bearer",
                credentials="some-token",
            )

            # verify_token이 sub 없는 클레임 반환하도록 mock
            with patch.object(oidc_client, "verify_token", new_callable=AsyncMock) as mock_verify:
                mock_verify.return_value = {
                    "iss": "https://issuer.example.com",
                    "aud": "test-client-id",
                    # sub 누락
                }

                with pytest.raises(HTTPException) as exc_info:
                    await get_current_user(request=mock_request, credentials=credentials)

                assert exc_info.value.status_code == 401
                assert "sub" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_oidc_enabled_valid_token(self):
        """유효한 토큰으로 CurrentUser 반환"""
        from app.core.auth import get_current_user, oidc_client

        mock_request = MagicMock()
        mock_request.state.current_user = None

        with patch("app.core.auth.settings") as mock_settings:
            mock_settings.OIDC_ENABLED = True

            credentials = HTTPAuthorizationCredentials(
                scheme="Bearer",
                credentials="valid-token",
            )

            claims = {
                "sub": "user-123",
                "email": "user@example.com",
                "name": "Valid User",
                "iss": "https://issuer.example.com",
                "aud": "test-client-id",
            }

            with patch.object(oidc_client, "verify_token", new_callable=AsyncMock) as mock_verify:
                mock_verify.return_value = claims

                user = await get_current_user(request=mock_request, credentials=credentials)

                assert user.sub == "user-123"
                assert user.email == "user@example.com"
                assert user.name == "Valid User"
                assert user.raw_claims == claims


# ============================================================================
# get_optional_current_user 테스트
# ============================================================================

class TestGetOptionalCurrentUser:
    """get_optional_current_user dependency 테스트"""

    @pytest.mark.asyncio
    async def test_oidc_disabled_returns_mock_user(self):
        """OIDC 비활성화 시 mock 사용자 반환"""
        from app.core.auth import get_optional_current_user

        mock_request = MagicMock()
        mock_request.state.current_user = None

        with patch("app.core.auth.settings") as mock_settings:
            mock_settings.OIDC_ENABLED = False

            user = await get_optional_current_user(request=mock_request, credentials=None)

            assert user is not None
            assert user.sub == "test-user-id"

    @pytest.mark.asyncio
    async def test_oidc_enabled_no_credentials_returns_none(self):
        """OIDC 활성화 상태에서 credentials 없으면 None 반환 (401 아님)"""
        from app.core.auth import get_optional_current_user

        mock_request = MagicMock()
        mock_request.state.current_user = None

        with patch("app.core.auth.settings") as mock_settings:
            mock_settings.OIDC_ENABLED = True

            user = await get_optional_current_user(request=mock_request, credentials=None)

            assert user is None

    @pytest.mark.asyncio
    async def test_oidc_enabled_invalid_token_returns_none(self):
        """OIDC 활성화 상태에서 잘못된 토큰이면 None 반환 (401 아님)"""
        from app.core.auth import get_optional_current_user, oidc_client

        mock_request = MagicMock()
        mock_request.state.current_user = None

        with patch("app.core.auth.settings") as mock_settings:
            mock_settings.OIDC_ENABLED = True

            credentials = HTTPAuthorizationCredentials(
                scheme="Bearer",
                credentials="invalid-token",
            )

            with patch.object(oidc_client, "verify_token", new_callable=AsyncMock) as mock_verify:
                mock_verify.side_effect = HTTPException(status_code=401, detail="Invalid token")

                user = await get_optional_current_user(request=mock_request, credentials=credentials)

                assert user is None

    @pytest.mark.asyncio
    async def test_oidc_enabled_valid_token_returns_user(self):
        """OIDC 활성화 상태에서 유효한 토큰이면 CurrentUser 반환"""
        from app.core.auth import get_optional_current_user, oidc_client

        mock_request = MagicMock()
        mock_request.state.current_user = None

        with patch("app.core.auth.settings") as mock_settings:
            mock_settings.OIDC_ENABLED = True

            credentials = HTTPAuthorizationCredentials(
                scheme="Bearer",
                credentials="valid-token",
            )

            claims = {
                "sub": "user-456",
                "email": "optional@example.com",
                "name": "Optional User",
                "iss": "https://issuer.example.com",
                "aud": "test-client-id",
            }

            with patch.object(oidc_client, "verify_token", new_callable=AsyncMock) as mock_verify:
                mock_verify.return_value = claims

                user = await get_optional_current_user(request=mock_request, credentials=credentials)

                assert user is not None
                assert user.sub == "user-456"


# ============================================================================
# AuthenticationRequiredError 테스트
# ============================================================================

class TestAuthenticationRequiredError:
    """AuthenticationRequiredError 테스트"""

    def test_error_attributes(self):
        """에러 속성 확인"""
        from app.core.error_handlers import AuthenticationRequiredError

        error = AuthenticationRequiredError()

        assert error.status_code == 401
        assert "인증" in error.detail
        assert "Bearer" in error.detail

    def test_custom_detail(self):
        """커스텀 메시지로 에러 생성"""
        from app.core.error_handlers import AuthenticationRequiredError

        error = AuthenticationRequiredError(detail="Custom auth error")

        assert error.detail == "Custom auth error"
        assert error.status_code == 401
