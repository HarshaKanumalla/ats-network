#backend/app/core/config.py

from typing import Dict, Any, Optional, List
import os
from pathlib import Path
import json
from datetime import timedelta
from functools import lru_cache
import logging
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    """Application configuration settings with environment variable support."""
    
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
    
    # Cookie Settings
    COOKIE_SECURE: bool = True
    COOKIE_DOMAIN: str
    COOKIE_SAMESITE: str = "lax"
    REFRESH_TOKEN_COOKIE_NAME: str = "refresh_token"
    
    # Monitoring Settings
    LOG_LEVEL: str = "INFO"
    ENABLE_REQUEST_LOGGING: bool = True
    SLOW_REQUEST_THRESHOLD_MS: int = 500
    MONITORING_ENABLED: bool = True
    
    # Rate Limiting Settings
    RATE_LIMIT_ENABLED: bool = True
    DEFAULT_RATE_LIMIT: str = "100/minute"
    AUTH_RATE_LIMIT: str = "20/minute"
    
    # Geographic Settings
    MAP_BOUNDS: Dict[str, float] = {
        "north": 37.5,  # Northernmost point of India
        "south": 6.5,   # Southernmost point
        "east": 97.5,   # Easternmost point
        "west": 68.0    # Westernmost point
    }
    
    # Test Session Settings
    MAX_TEST_DURATION_MINUTES: int = 120
    TEST_TYPES: List[str] = [
        "speed",
        "brake",
        "noise",
        "headlight",
        "axle"
    ]
    TEST_STATUS_OPTIONS: List[str] = [
        "scheduled",
        "in_progress",
        "completed",
        "failed",
        "cancelled"
    ]
    
    # Document Settings
    MAX_UPLOAD_SIZE_MB: int = 10
    ALLOWED_DOCUMENT_TYPES: List[str] = [
        "application/pdf",
        "image/jpeg",
        "image/png",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ]
    
    # Role and Permission Settings
    USER_ROLES: List[str] = [
        "transport_commissioner",
        "additional_commissioner",
        "rto_officer",
        "ats_owner",
        "ats_admin",
        "ats_testing"
    ]

    # Storage Settings (missing in current version)
    TEMP_FILE_DIR: str = "/tmp/ats_network"
    DOCUMENT_STORAGE_PATH: str = "/storage/documents"
    FILE_CLEANUP_INTERVAL: int = 3600  # seconds

    # Redis Enhanced Settings (additional security settings)
    REDIS_SSL: bool = False
    REDIS_CONNECTION_TIMEOUT: int = 30
    REDIS_MAX_CONNECTIONS: int = 100
    REDIS_RETRY_ON_TIMEOUT: bool = True

    # Backup Settings (missing in current version)
    BACKUP_ENABLED: bool = True
    BACKUP_INTERVAL_HOURS: int = 24
    BACKUP_RETENTION_DAYS: int = 30
    BACKUP_S3_PREFIX: str = "backups/"

    # Security Enhanced Settings (additional security parameters)
    PASSWORD_MIN_LENGTH: int = 8
    PASSWORD_HISTORY_SIZE: int = 5
    FAILED_LOGIN_ATTEMPTS: int = 5
    ACCOUNT_LOCKOUT_MINUTES: int = 30
    
    # Session Settings (missing in current version)
    SESSION_TIMEOUT_MINUTES: int = 60
    MAX_SESSIONS_PER_USER: int = 5
    SESSION_CLEANUP_INTERVAL: int = 3600  # seconds
    
    class Config:
        """Configuration for the settings class."""
        env_file = ".env"
        case_sensitive = True
        
        @classmethod
        def customise_sources(
            cls,
            init_settings,
            env_settings,
            file_secret_settings
        ):
            """Customize settings load order."""
            return (
                init_settings,
                env_settings,
                file_secret_settings
            )

    @property
    def database_settings(self) -> Dict[str, Any]:
        """Get database-specific settings."""
        return {
            "url": self.MONGODB_URL,
            "db_name": self.MONGODB_DB_NAME,
            "min_pool_size": self.MONGODB_MIN_POOL_SIZE,
            "max_pool_size": self.MONGODB_MAX_POOL_SIZE,
            "timeout_ms": self.MONGODB_TIMEOUT_MS
        }

    @property
    def jwt_settings(self) -> Dict[str, Any]:
        """Get JWT authentication settings."""
        return {
            "secret_key": self.SECRET_KEY,
            "algorithm": self.TOKEN_ALGORITHM,
            "access_token_expire_minutes": self.ACCESS_TOKEN_EXPIRE_MINUTES,
            "refresh_token_expire_days": self.REFRESH_TOKEN_EXPIRE_DAYS,
        }

    @property
    def aws_settings(self) -> Dict[str, Any]:
        """Get AWS service settings."""
        return {
            "access_key_id": self.AWS_ACCESS_KEY_ID,
            "secret_access_key": self.AWS_SECRET_ACCESS_KEY,
            "region": self.AWS_REGION,
            "s3_bucket": self.S3_BUCKET_NAME
        }

    @property
    def email_settings(self) -> Dict[str, Any]:
        """Get email service settings."""
        return {
            "server": self.MAIL_SERVER,
            "port": self.MAIL_PORT,
            "username": self.MAIL_USERNAME,
            "password": self.MAIL_PASSWORD,
            "from_address": self.MAIL_FROM,
            "use_tls": self.MAIL_TLS,
            "use_ssl": self.MAIL_SSL
        }

@property
    def redis_settings(self) -> Dict[str, Any]:
        """Get enhanced Redis connection settings."""
        return {
            "host": self.REDIS_HOST,
            "port": self.REDIS_PORT,
            "password": self.REDIS_PASSWORD,
            "db": self.REDIS_DB,
            "ssl": self.REDIS_SSL,
            "connection_timeout": self.REDIS_CONNECTION_TIMEOUT,
            "max_connections": self.REDIS_MAX_CONNECTIONS,
            "retry_on_timeout": self.REDIS_RETRY_ON_TIMEOUT,
            "decode_responses": True
        }

    def get_environment_variables(self) -> Dict[str, str]:
        """Get all environment variables (excluding secrets)."""
        return {
            key: value for key, value in os.environ.items()
            if not key.lower().contains(("secret", "password", "key"))
        }

    def validate_settings(self) -> None:
        """Validate required settings and their values."""
        # Validate database URL format
        if not self.MONGODB_URL.startswith(("mongodb://", "mongodb+srv://")):
            raise ValueError("Invalid MongoDB URL format")
        
        # Validate email settings
        if self.MAIL_SSL and self.MAIL_TLS:
            raise ValueError("Cannot enable both SSL and TLS for email")
        
        # Validate rate limits
        for rate_limit in [self.DEFAULT_RATE_LIMIT, self.AUTH_RATE_LIMIT]:
            if not self._is_valid_rate_limit(rate_limit):
                raise ValueError(f"Invalid rate limit format: {rate_limit}")
        
        # Validate geographic bounds
        for bound in self.MAP_BOUNDS.values():
            if not isinstance(bound, (int, float)):
                raise ValueError("Invalid geographic bound value")

    def _is_valid_rate_limit(self, rate_limit: str) -> bool:
        """Validate rate limit format."""
        try:
            count, period = rate_limit.split("/")
            return (
                count.isdigit() and
                period in ["second", "minute", "hour", "day"]
            )
        except ValueError:
            return False

@lru_cache()
def get_settings() -> Settings:
    """Get application settings with caching.
    
    Returns:
        Settings instance
        
    Note:
        Uses LRU cache to prevent repeated environment variable reads
    """
    settings = Settings()
    settings.validate_settings()
    return settings

def initialize_logging() -> None:
    """Initialize application logging configuration."""
    settings = get_settings()
    
    logging.basicConfig(
        level=settings.LOG_LEVEL,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('app.log')
        ]
    )
    
    # Set third-party package log levels
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("motor").setLevel(logging.WARNING)

def configure_environment() -> None:
    """Configure application environment based on settings."""
    settings = get_settings()
    
    # Set environment-specific configurations
    if settings.ENVIRONMENT == "development":
        configure_development()
    elif settings.ENVIRONMENT == "production":
        configure_production()
    elif settings.ENVIRONMENT == "testing":
        configure_testing()

def configure_development() -> None:
    """Configure development environment settings."""
    os.environ["PYTHONPATH"] = str(Path(__file__).parent.parent)
    os.environ["PYTHONASYNCIODEBUG"] = "1"

def configure_production() -> None:
    """Configure production environment settings."""
    # Disable debug modes
    os.environ["PYTHONPATH"] = str(Path(__file__).parent.parent)
    os.environ["PYTHONASYNCIODEBUG"] = "0"

def configure_testing() -> None:
    """Configure test environment settings."""
    os.environ["TESTING"] = "1"
    os.environ["PYTHONPATH"] = str(Path(__file__).parent.parent)