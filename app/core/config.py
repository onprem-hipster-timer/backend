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

    # API 문서
    DOCS_ENABLED: bool = True  # Swagger/ReDoc 문서 활성화 (개발 환경에서만 True)

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

    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=True,
    )

    @model_validator(mode="after")
    def apply_production_defaults(self) -> Self:
        """프로덕션 환경에서는 보안 관련 설정을 자동으로 비활성화"""
        if self.ENVIRONMENT == "production":
            # 프로덕션에서는 디버그 및 문서 관련 기능 비활성화
            object.__setattr__(self, "DEBUG", False)
            object.__setattr__(self, "DOCS_ENABLED", False)
            object.__setattr__(self, "GRAPHQL_ENABLE_PLAYGROUND", False)
            object.__setattr__(self, "GRAPHQL_ENABLE_INTROSPECTION", False)
        return self


settings = Settings()
