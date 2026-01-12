"""
OIDC 인증 모듈

Authlib를 사용한 OIDC discovery 및 JWT Access Token 검증.
모든 API 엔드포인트를 보호하고 CurrentUser 컨텍스트를 제공합니다.
"""
import logging
from typing import Any

import httpx
from authlib.jose import JsonWebKey, jwt
from authlib.jose.errors import JoseError
from cachetools import TTLCache
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.config import settings

logger = logging.getLogger(__name__)

# HTTP Bearer 스키마
security = HTTPBearer(auto_error=False)


class CurrentUser(BaseModel):
    """현재 인증된 사용자 정보 (JWT 클레임에서 추출)"""
    sub: str  # 사용자 고유 식별자 (owner_id로 사용)
    email: str | None = None
    name: str | None = None
    
    # 추가 클레임 (필요시 확장)
    raw_claims: dict[str, Any] = {}


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
    
    async def get_jwks(self) -> JsonWebKey:
        """
        JWKS (JSON Web Key Set) 조회 (캐싱됨)
        
        Returns:
            Authlib JsonWebKey 객체
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
        
        jwks = JsonWebKey.import_key_set(jwks_data)
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
            
            # JWT 디코딩 및 서명 검증
            claims = jwt.decode(token, jwks)
            
            # 클레임 검증
            claims.validate()
            
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
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch JWKS: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service unavailable",
            )


# 싱글톤 OIDC 클라이언트 인스턴스
oidc_client = OIDCClient()


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> CurrentUser:
    """
    FastAPI Dependency: 현재 인증된 사용자 반환
    
    - AuthMiddleware에서 이미 검증된 경우 request.state에서 가져옴 (중복 검증 방지)
    - 그렇지 않으면 Authorization: Bearer <token> 헤더에서 토큰 추출 후 검증
    - CurrentUser 객체 반환
    
    OIDC_ENABLED=false인 경우 테스트용 mock 사용자 반환
    """
    # AuthMiddleware에서 이미 검증된 경우 재사용
    if hasattr(request.state, 'current_user') and request.state.current_user:
        return request.state.current_user
    
    # 인증 비활성화 시 테스트용 사용자 반환
    if not settings.OIDC_ENABLED:
        return CurrentUser(
            sub="test-user-id",
            email="test@example.com",
            name="Test User",
        )
    
    # 토큰 없음
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 토큰 검증
    claims = await oidc_client.verify_token(credentials.credentials)
    
    # sub 클레임 필수
    sub = claims.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing 'sub' claim",
        )
    
    return CurrentUser(
        sub=sub,
        email=claims.get("email"),
        name=claims.get("name"),
        raw_claims=claims,
    )


async def get_optional_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> CurrentUser | None:
    """
    FastAPI Dependency: 선택적 인증 (인증 없어도 접근 가능한 엔드포인트용)
    
    토큰이 없으면 None 반환, 토큰이 있으면 검증 후 CurrentUser 반환
    """
    # AuthMiddleware에서 이미 검증된 경우 재사용
    if hasattr(request.state, 'current_user') and request.state.current_user:
        return request.state.current_user
    
    if not settings.OIDC_ENABLED:
        return CurrentUser(
            sub="test-user-id",
            email="test@example.com",
            name="Test User",
        )
    
    if not credentials:
        return None
    
    try:
        return await get_current_user(request, credentials)
    except HTTPException:
        return None


class AuthMiddleware(BaseHTTPMiddleware):
    """
    인증 미들웨어 - request.state.current_user 설정
    
    토큰 검증 결과를 request.state에 저장하여 
    다른 미들웨어(RateLimitMiddleware 등)나 Depends에서 중복 검증 없이 사용 가능
    
    처리 흐름:
    1. Authorization 헤더에서 Bearer 토큰 추출
    2. OIDC Provider를 통해 JWT 검증
    3. 검증 성공 시 request.state.current_user에 CurrentUser 저장
    4. 검증 실패/토큰 없음 시 request.state.current_user = None
    """
    
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        # 기본값 설정 (미인증 상태)
        request.state.current_user = None
        
        # OIDC 비활성화 시 테스트 사용자
        if not settings.OIDC_ENABLED:
            request.state.current_user = CurrentUser(
                sub="test-user-id",
                email="test@example.com",
                name="Test User",
            )
            return await call_next(request)
        
        # Authorization 헤더 확인
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                claims = await oidc_client.verify_token(token)
                sub = claims.get("sub")
                if sub:
                    request.state.current_user = CurrentUser(
                        sub=sub,
                        email=claims.get("email"),
                        name=claims.get("name"),
                        raw_claims=claims,
                    )
            except Exception:
                # 토큰 검증 실패 - 미인증 상태로 진행
                # 실제 인증 에러는 엔드포인트의 get_current_user에서 처리
                pass
        
        return await call_next(request)
