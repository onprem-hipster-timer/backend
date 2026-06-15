"""
OIDC 클라이언트

joserfc를 사용한 OIDC discovery, JWKS 캐싱, JWT Access Token 검증.
이 서버는 OIDC Resource Server(Relying Party)로서 외부 Provider 발급 토큰을 검증한다.
"""
import logging
from typing import Any

import httpx
from cachetools import TTLCache
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet
from joserfc.jwt import JWTClaimsRegistry
from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)

# 허용 서명 알고리즘 (비대칭만 허용 — alg 혼동/none 공격 방지)
ALLOWED_JWT_ALGORITHMS = ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"]

# JWT 표준 클레임(exp/nbf/iat) 검증 레지스트리
_claims_registry = JWTClaimsRegistry()


class OIDCClient:
    """
    외부 OIDC Provider와 통신하는 클라이언트

    - OIDC discovery를 통해 issuer 메타데이터 로딩
    - JWKS 캐싱 (TTL 기반)
    - JWT Access Token 검증

    Note: 이 서버는 OIDC Resource Server (Relying Party)입니다.
    외부 OIDC Provider(Keycloak, Auth0 등)에서 발급한 토큰을 검증합니다.
    """

    def __init__(self):
        self._metadata_cache: TTLCache = TTLCache(
            maxsize=1,
            ttl=settings.OIDC_JWKS_CACHE_TTL_SECONDS
        )
        self._jwks_cache: TTLCache = TTLCache(
            maxsize=1,
            ttl=settings.OIDC_JWKS_CACHE_TTL_SECONDS
        )

    @property
    def discovery_url(self) -> str:
        """OIDC discovery endpoint URL"""
        if settings.OIDC_DISCOVERY_URL:
            return settings.OIDC_DISCOVERY_URL
        return f"{settings.OIDC_ISSUER_URL.rstrip('/')}/.well-known/openid-configuration"

    async def get_metadata(self) -> dict[str, Any]:
        """
        OIDC Provider 메타데이터 조회 (캐싱됨)

        Returns:
            OpenID Provider Configuration (issuer, jwks_uri, etc.)
        """
        cache_key = "metadata"
        if cache_key in self._metadata_cache:
            return self._metadata_cache[cache_key]

        async with httpx.AsyncClient() as client:
            response = await client.get(self.discovery_url)
            response.raise_for_status()
            metadata = response.json()

        self._metadata_cache[cache_key] = metadata
        logger.info(f"OIDC metadata loaded from {self.discovery_url}")
        return metadata

    async def get_jwks(self) -> KeySet:
        """
        JWKS (JSON Web Key Set) 조회 (캐싱됨)

        Returns:
            joserfc KeySet 객체
        """
        cache_key = "jwks"
        if cache_key in self._jwks_cache:
            return self._jwks_cache[cache_key]

        metadata = await self.get_metadata()
        jwks_uri = metadata.get("jwks_uri")
        if not jwks_uri:
            raise ValueError("OIDC metadata does not contain jwks_uri")

        async with httpx.AsyncClient() as client:
            response = await client.get(jwks_uri)
            response.raise_for_status()
            jwks_data = response.json()

        jwks = KeySet.import_key_set(jwks_data)
        self._jwks_cache[cache_key] = jwks
        logger.info(f"JWKS loaded from {jwks_uri}")
        return jwks

    async def verify_token(self, token: str) -> dict[str, Any]:
        """
        JWT Access Token 검증

        Args:
            token: Bearer 토큰 문자열

        Returns:
            검증된 JWT 클레임

        Raises:
            HTTPException: 토큰 검증 실패 시
        """
        try:
            jwks = await self.get_jwks()

            # JWT 디코딩 및 서명 검증 (허용된 비대칭 알고리즘만)
            decoded = jwt.decode(token, jwks, algorithms=ALLOWED_JWT_ALGORITHMS)
            claims = decoded.claims

            # 표준 클레임(exp/nbf/iat) 검증
            _claims_registry.validate(claims)

            # issuer 검증
            if claims.get("iss") != settings.OIDC_ISSUER_URL:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Invalid issuer: {claims.get('iss')}",
                )

            # audience 검증 (aud는 문자열 또는 리스트일 수 있음)
            aud = claims.get("aud")
            if isinstance(aud, str):
                aud_list = [aud]
            else:
                aud_list = aud or []

            if settings.OIDC_AUDIENCE and settings.OIDC_AUDIENCE not in aud_list:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid audience",
                )

            return dict(claims)

        except JoseError as e:
            logger.warning(f"JWT verification failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {str(e)}",
            )
        except httpx.HTTPError:
            logger.exception("Failed to fetch JWKS")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service unavailable",
            )


# 싱글톤 OIDC 클라이언트 인스턴스
oidc_client = OIDCClient()
