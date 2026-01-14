from typing import Literal, Self

from pydantic import ConfigDict, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """애플리케이션 설정"""

    # 환경 설정
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"

    # 애플리케이션
    APP_NAME: str = "onperm-hipster-timer-backend"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # 데이터베이스
    DATABASE_URL: str = "sqlite:///./schedule.db"
    TEST_DATABASE_URL: str | None = None  # 테스트용 데이터베이스 URL
    POOL_SIZE: int = 5
    MAX_OVERFLOW: int = 10
    DB_POOL_PRE_PING: bool = True  # 연결 유효성 검사 (PostgreSQL 권장)
    DB_POOL_RECYCLE: int = 3600  # 연결 재활용 시간 (초, PostgreSQL 권장)

    # 로깅
    LOG_LEVEL: str = "INFO"

    # API 문서 (DOCS_ENABLED=False로 모든 문서 비활성화)
    DOCS_ENABLED: bool = True  # 모든 API 문서 비활성화 마스터 스위치 (Swagger, ReDoc, GraphQL Sandbox 포함)
    OPENAPI_URL: str = "/openapi.json"  # OpenAPI 스키마 URL (빈 문자열이면 비활성화)
    DOCS_URL: str = "/docs"  # Swagger UI URL (빈 문자열이면 비활성화)
    REDOC_URL: str = "/redoc"  # ReDoc URL (빈 문자열이면 비활성화)

    # GraphQL
    GRAPHQL_ENABLE_PLAYGROUND: bool = True  # 개발 환경에서만 True
    GRAPHQL_ENABLE_INTROSPECTION: bool = True  # 개발 환경에서만 True

    # 국경일 정보 API (한국천문연구원)
    HOLIDAY_API_BASE_URL: str = "http://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService"
    HOLIDAY_API_SERVICE_KEY: str = ""  # 공공데이터포털에서 발급받은 ServiceKey

    # OIDC 인증 설정
    OIDC_ENABLED: bool = True  # False로 설정하면 인증 비활성화 (개발/테스트용)
    OIDC_ISSUER_URL: str = ""  # 예: https://accounts.google.com, https://your-keycloak/realms/your-realm
    OIDC_AUDIENCE: str = ""  # Client ID (Access Token의 aud 클레임과 매칭)
    OIDC_DISCOVERY_URL: str | None = None  # 기본: OIDC_ISSUER_URL/.well-known/openid-configuration
    OIDC_JWKS_CACHE_TTL_SECONDS: int = 3600  # JWKS 캐시 TTL (기본 1시간)

    # Rate Limit 설정
    RATE_LIMIT_ENABLED: bool = True  # False로 설정하면 레이트 리밋 비활성화
    RATE_LIMIT_DEFAULT_WINDOW: int = 60  # 기본 윈도우 크기 (초)
    RATE_LIMIT_DEFAULT_REQUESTS: int = 60  # 기본 최대 요청 수

    # 프록시 설정
    PROXY_FORCE: bool = False  # 프록시/Cloudflare 경유 강제 (request.client.host 기준으로 프록시가 아니면 차단)

    # Cloudflare 프록시 설정
    CF_ENABLED: bool = False  # Cloudflare 프록시 사용 여부 (True: CF-Connecting-IP 헤더 신뢰)
    CF_IP_CACHE_TTL: int = 86400  # Cloudflare IP 목록 캐시 TTL (초, 기본 24시간)

    # Trusted Proxy 설정 (CF_ENABLED=False일 때 사용)
    TRUSTED_PROXY_IPS: str = ""  # 신뢰할 프록시 IP 목록 (콤마 구분, CIDR 지원, 예: "127.0.0.1,10.0.0.0/8")

    # CORS 설정
    CORS_ALLOWED_ORIGINS: str = "*"  # 허용할 origin (콤마로 구분, 예: "http://localhost:3000,https://example.com")
    CORS_ALLOW_CREDENTIALS: bool = False  # 자격 증명(쿠키 등) 허용 여부 (origin이 "*"일 때는 False여야 함)
    CORS_ALLOW_METHODS: str = "*"  # 허용할 HTTP 메서드 (콤마로 구분, 예: "GET,POST,PUT,DELETE")
    CORS_ALLOW_HEADERS: str = "*"  # 허용할 헤더 (콤마로 구분)

    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=True,
    )

    @model_validator(mode="after")
    def apply_production_defaults(self) -> Self:
        """프로덕션 환경 또는 DOCS_ENABLED=False일 때 문서 관련 설정 비활성화"""
        # DOCS_ENABLED=False면 모든 문서 비활성화
        if not self.DOCS_ENABLED:
            object.__setattr__(self, "OPENAPI_URL", "")
            object.__setattr__(self, "DOCS_URL", "")
            object.__setattr__(self, "REDOC_URL", "")
            object.__setattr__(self, "GRAPHQL_ENABLE_PLAYGROUND", False)
            object.__setattr__(self, "GRAPHQL_ENABLE_INTROSPECTION", False)

        if self.ENVIRONMENT == "production":
            # 프로덕션에서는 디버그 및 문서 관련 기능 비활성화
            object.__setattr__(self, "DEBUG", False)
            object.__setattr__(self, "OPENAPI_URL", "")
            object.__setattr__(self, "DOCS_URL", "")
            object.__setattr__(self, "REDOC_URL", "")
            object.__setattr__(self, "GRAPHQL_ENABLE_PLAYGROUND", False)
            object.__setattr__(self, "GRAPHQL_ENABLE_INTROSPECTION", False)
        return self

    @property
    def cors_origins(self) -> list[str]:
        """CORS_ALLOWED_ORIGINS를 리스트로 반환"""
        if self.CORS_ALLOWED_ORIGINS == "*":
            return ["*"]
        return [origin.strip() for origin in self.CORS_ALLOWED_ORIGINS.split(",") if origin.strip()]

    @property
    def cors_methods(self) -> list[str]:
        """CORS_ALLOW_METHODS를 리스트로 반환"""
        if self.CORS_ALLOW_METHODS == "*":
            return ["*"]
        return [method.strip() for method in self.CORS_ALLOW_METHODS.split(",") if method.strip()]

    @property
    def cors_headers(self) -> list[str]:
        """CORS_ALLOW_HEADERS를 리스트로 반환"""
        if self.CORS_ALLOW_HEADERS == "*":
            return ["*"]
        return [header.strip() for header in self.CORS_ALLOW_HEADERS.split(",") if header.strip()]

    @property
    def trusted_proxy_ips(self) -> list[str]:
        """TRUSTED_PROXY_IPS를 리스트로 반환"""
        if not self.TRUSTED_PROXY_IPS:
            return []
        return [ip.strip() for ip in self.TRUSTED_PROXY_IPS.split(",") if ip.strip()]


settings = Settings()
