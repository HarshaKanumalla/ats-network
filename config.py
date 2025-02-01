# backend/config.py

from pydantic_settings import BaseSettings
from typing import List
from functools import lru_cache
import os

class Settings(BaseSettings):
    # Application settings
    PROJECT_NAME: str = "ATS Network API"
    VERSION: str = "1.0.0"
    DEBUG: bool = False
    API_PREFIX: str = "/api/v1"
    
    # Security settings
    ACCESS_TOKEN_SECRET: str
    REFRESH_TOKEN_SECRET: str
    TOKEN_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15  # Short-lived token
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7    # Long-lived token
    ADMIN_EMAIL: str = "atsnetwork15@gmail.com"
    ADMIN_PASSWORD: str = "Admin@123"
    
    # JWT Settings
    JWT_PUBLIC_KEY: str
    JWT_PRIVATE_KEY: str
    REFRESH_TOKEN_COOKIE_NAME: str = "refreshToken"
    
    # CORS settings
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]
    CORS_CREDENTIALS: bool = True
    
    # Database settings
    MONGODB_URL: str
    MONGODB_DB_NAME: str = "ats_network"
    
    # AWS settings
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_REGION: str
    S3_BUCKET_NAME: str
    
    # Email settings
    SMTP_SERVER: str
    SMTP_PORT: int
    SMTP_USERNAME: str
    SMTP_PASSWORD: str
    MAIL_FROM: str
    MAIL_FROM_NAME: str
    
    # WebSocket settings
    WS_URL: str = "ws://localhost:8000/ws"
    
    # Redis settings (for session and token management)
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str
    REDIS_DB: int = 0
    
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

    class Config:
        env_file = ".env"
        case_sensitive = True

@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()