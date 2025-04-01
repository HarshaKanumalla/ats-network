# backend/app/core/config.py

from typing import Dict, Any, Optional, List
import os
from pathlib import Path
from datetime import timedelta
from functools import lru_cache
import logging
from pydantic import BaseSettings

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    """
    Application configuration settings with environment variable support.

    Attributes:
        ENVIRONMENT (str): The current environment (e.g., development, production).
        DEBUG (bool): Whether debug mode is enabled.
        SECRET_KEY (str): The secret key for signing tokens.
        ...
    """
    
    # Environment Configuration
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    TESTING: bool = False
    
    # Application Settings
    APP_NAME: str = "ATS Network"
    APP_VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"
    WORKERS_COUNT: int = 4
    
    # Security Settings
    SECRET_KEY: str
    ACCESS_TOKEN_SECRET: str
    REFRESH_TOKEN_SECRET: str
    TOKEN_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    PASSWORD_HASH_ALGORITHM: str = "bcrypt"
    ENCRYPTION_SALT: str
    MASTER_KEY: str
    
    # Database Settings
    MONGODB_URL: str
    MONGODB_DB_NAME: str
    MONGODB_MIN_POOL_SIZE: int = 10
    MONGODB_MAX_POOL_SIZE: int = 100
    MONGODB_TIMEOUT_MS: int = 5000
    
    # Redis Settings
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: Optional[str] = None
    REDIS_DB: int = 0
    REDIS_SSL: bool = False
    REDIS_CONNECTION_TIMEOUT: int = 30
    REDIS_MAX_CONNECTIONS: int = 100
    REDIS_RETRY_ON_TIMEOUT: bool = True

    # Email Settings
    MAIL_SERVER: str
    MAIL_PORT: int
    MAIL_USERNAME: str
    MAIL_PASSWORD: str
    MAIL_FROM: str
    MAIL_TLS: bool = True
    MAIL_SSL: bool = False
    ADMIN_EMAIL: str
    SUPPORT_EMAIL: str
    
    # AWS Settings
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_REGION: str
    S3_BUCKET_NAME: str
    
    # Frontend Settings
    FRONTEND_URL: str
    ALLOWED_ORIGINS: List[str]
    
    # Monitoring Settings
    LOG_LEVEL: str = "INFO"
    ENABLE_REQUEST_LOGGING: bool = True
    SLOW_REQUEST_THRESHOLD_MS: int = 500
    MONITORING_ENABLED: bool = True
    
    # Rate Limiting Settings
    RATE_LIMIT_ENABLED: bool = True
    DEFAULT_RATE_LIMIT: str = "100/minute"
    AUTH_RATE_LIMIT: str = "20/minute"
    
    class Config:
        """Configuration for the settings class."""
        env_file = ".env"
        case_sensitive = True

    def validate_settings(self) -> None:
        """Validate required settings and their values."""
        if not self.SECRET_KEY:
            raise ValueError("SECRET_KEY is required")
        if not self.MONGODB_URL.startswith(("mongodb://", "mongodb+srv://")):
            raise ValueError("Invalid MongoDB URL format")
        if not self.MAIL_SERVER:
            raise ValueError("MAIL_SERVER is required")
        if self.MAIL_SSL and self.MAIL_TLS:
            raise ValueError("Cannot enable both SSL and TLS for email")
        for rate_limit in [self.DEFAULT_RATE_LIMIT, self.AUTH_RATE_LIMIT]:
            if not self._is_valid_rate_limit(rate_limit):
                raise ValueError(f"Invalid rate limit format: {rate_limit}")

    def _is_valid_rate_limit(self, rate_limit: str) -> bool:
        """Validate rate limit format."""
        try:
            count, period = rate_limit.split("/")
            return count.isdigit() and period in ["second", "minute", "hour", "day"]
        except ValueError:
            return False

@lru_cache()
def get_settings() -> Settings:
    """Get application settings with caching."""
    settings = Settings()
    settings.validate_settings()
    return settings

def initialize_logging() -> None:
    """Initialize application logging configuration."""
    settings = get_settings()
    logging.basicConfig(
        level=settings.LOG_LEVEL,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("app.log")
        ]
    )
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("motor").setLevel(logging.WARNING)