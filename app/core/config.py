from pydantic_settings import BaseSettings
from pydantic import ConfigDict


class Settings(BaseSettings):
    """애플리케이션 설정"""

    # 애플리케이션
    APP_NAME: str = "onperm-hipster-timer-backend"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # 데이터베이스
    DATABASE_URL: str = "sqlite:///./schedule.db"
    POOL_SIZE: int = 5
    MAX_OVERFLOW: int = 10

    # 로깅
    LOG_LEVEL: str = "INFO"

    # GraphQL
    GRAPHQL_ENABLE_PLAYGROUND: bool = True  # 개발 환경에서만 True
    GRAPHQL_ENABLE_INTROSPECTION: bool = True  # 개발 환경에서만 True

    # 국경일 정보 API (한국천문연구원)
    HOLIDAY_API_BASE_URL: str = "http://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService"
    HOLIDAY_API_SERVICE_KEY: str = ""  # 공공데이터포털에서 발급받은 ServiceKey

    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=True,
    )


settings = Settings()
