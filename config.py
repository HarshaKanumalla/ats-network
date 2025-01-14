# backend/app/config.py
from pydantic_settings import BaseSettings
from typing import List
from functools import lru_cache
import os
from datetime import datetime

# System Info
SYSTEM_INFO = {
    "last_updated": "2024-12-19 18:24:36",
    "updated_by": "HarshaKanumalla"
}

class Settings(BaseSettings):
    # Application settings
    environment: str = "development"
    workers_count: int = 1
    debug: bool = True

    # Security settings
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    algorithm: str = "HS256"  
    jwt_expiration: int = 30
    secret_key: str

    # Database settings
    mongodb_url: str
    database_name: str = "ats_network"

    # Email settings
    mail_username: str
    mail_password: str
    mail_from: str
    mail_port: int = 587
    mail_server: str = "smtp.gmail.com"
    mail_tls: bool = True
    mail_ssl: bool = False
    admin_email: str
    support_email: str = ""

    # Frontend settings
    frontend_url: str = "http://localhost:3000"
    allowed_origins: List[str] = ["http://localhost:3000"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

        # Aliases for environment variables
        fields = {
            "jwt_secret": {"env": ["JWT_SECRET", "SECRET_KEY"]},
            "jwt_algorithm": {"env": ["JWT_ALGORITHM", "ALGORITHM"]},
            "jwt_expiration": {"env": ["JWT_EXPIRATION", "ACCESS_TOKEN_EXPIRE_MINUTES"]},
            "mongodb_url": {"env": ["MONGODB_URL", "DATABASE_URL"]},
            "mail_username": {"env": ["MAIL_USERNAME", "EMAIL_USERNAME"]},
            "mail_password": {"env": ["MAIL_PASSWORD", "EMAIL_PASSWORD"]},
            "mail_from": {"env": ["MAIL_FROM", "EMAIL_FROM"]},
            "mail_port": {"env": ["MAIL_PORT", "EMAIL_PORT"]},
            "mail_server": {"env": ["MAIL_SERVER", "EMAIL_SERVER"]},
            "mail_tls": {"env": ["MAIL_TLS", "EMAIL_USE_TLS"]},
            "mail_ssl": {"env": ["MAIL_SSL", "EMAIL_USE_SSL"]},
        }

@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()