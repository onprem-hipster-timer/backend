from pydantic_settings import BaseSettings


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
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

