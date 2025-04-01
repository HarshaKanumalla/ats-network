# backend/config.py

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List, Optional
from functools import lru_cache

class Settings(BaseSettings):
    # Application settings
    PROJECT_NAME: str = "ATS Network API"
    VERSION: str = "1.0.0"
    DEBUG: bool = Field(default=False, env="DEBUG")
    API_PREFIX: str = "/api/v1"
    
    # Security settings
    ACCESS_TOKEN_SECRET: str = Field(..., env="ACCESS_TOKEN_SECRET")
    REFRESH_TOKEN_SECRET: str = Field(..., env="REFRESH_TOKEN_SECRET")
    TOKEN_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15  # Short-lived token
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7    # Long-lived token
    ADMIN_EMAIL: str = Field(..., env="ADMIN_EMAIL")
    ADMIN_PASSWORD: str = Field(..., env="ADMIN_PASSWORD")
    
    # JWT Settings
    JWT_PUBLIC_KEY: str = Field(..., env="JWT_PUBLIC_KEY")
    JWT_PRIVATE_KEY: str = Field(..., env="JWT_PRIVATE_KEY")
    REFRESH_TOKEN_COOKIE_NAME: str = "refreshToken"
    
    # CORS settings
    CORS_ORIGINS: List[str] = Field(default=["http://localhost:3000"], env="CORS_ORIGINS")
    CORS_CREDENTIALS: bool = True
    
    # Database settings
    MONGODB_URL: str = Field(..., env="MONGODB_URL")
    MONGODB_DB_NAME: str = "ats_network"
    
    # AWS settings
    AWS_ACCESS_KEY_ID: Optional[str] = Field(default=None, env="AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY: Optional[str] = Field(default=None, env="AWS_SECRET_ACCESS_KEY")
    AWS_REGION: Optional[str] = Field(default=None, env="AWS_REGION")
    S3_BUCKET_NAME: Optional[str] = Field(default=None, env="S3_BUCKET_NAME")
    
    # Email settings
    SMTP_SERVER: str = Field(..., env="SMTP_SERVER")
    SMTP_PORT: int = Field(..., env="SMTP_PORT")
    SMTP_USERNAME: str = Field(..., env="SMTP_USERNAME")
    SMTP_PASSWORD: str = Field(..., env="SMTP_PASSWORD")
    MAIL_FROM: str = Field(..., env="MAIL_FROM")
    MAIL_FROM_NAME: str = Field(..., env="MAIL_FROM_NAME")
    
    # WebSocket settings
    WS_URL: str = Field(default="ws://localhost:8000/ws", env="WS_URL")
    
    # Redis settings (for session and token management)
    REDIS_HOST: str = Field(default="localhost", env="REDIS_HOST")
    REDIS_PORT: int = Field(default=6379, env="REDIS_PORT")
    REDIS_PASSWORD: Optional[str] = Field(default=None, env="REDIS_PASSWORD")
    REDIS_DB: int = Field(default=0, env="REDIS_DB")
    
    # Role-based access settings
    ROLE_HIERARCHY = {
        "transport_commissioner": ["all"],
        "additional_commissioner": ["all"],
        "super_admin": ["all"],
        "rto_officer": ["approve_tests", "view_all_centers", "view_all_reports"],
        "ats_owner": ["manage_center", "view_center_reports", "manage_staff"],
        "ats_admin": ["manage_tests", "view_center_reports"],
        "ats_testing": ["conduct_tests", "view_test_reports"]
    }

    # Logging settings
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")
    LOG_FILE_PATH: Optional[str] = Field(default=None, env="LOG_FILE_PATH")

    class Config:
        env_file = ".env"
        case_sensitive = True

@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()