from pydantic_settings import BaseSettings
from typing import List, Optional
from functools import lru_cache
from datetime import timedelta

class Settings(BaseSettings):
    # Application settings
    environment: str = "development"
    workers_count: int = 1
    debug: bool = True
    api_prefix: str = "/api/v1"

    # Security settings
    access_token_secret: str
    refresh_token_secret: str
    token_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Cookie settings
    cookie_secure: bool = True
    cookie_domain: str = "localhost"
    cookie_samesite: str = "lax"

    # Database settings
    mongodb_url: str
    database_name: str = "ats_network"

    # Redis settings
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None

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

    # File upload settings
    upload_folder: str = "uploads"
    max_upload_size: int = 5 * 1024 * 1024  # 5MB
    allowed_extensions: List[str] = ["pdf", "doc", "docx"]

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "env_prefix": "",
        "use_enum_values": True,
        "extra": "allow",
        "env_nested_delimiter": "__",
        "validate_default": True,
        "protected_namespaces": ("model_", "validate_", "json_", "parse_"),
        "alias_generator": None,
        "str_strip_whitespace": True,
        "env_vars_override": True,
        "env_mapping": {
            "access_token_secret": ["ACCESS_TOKEN_SECRET", "JWT_SECRET"],
            "refresh_token_secret": ["REFRESH_TOKEN_SECRET", "SECRET_KEY"],
            "token_algorithm": ["TOKEN_ALGORITHM", "JWT_ALGORITHM"],
            "access_token_expire_minutes": ["ACCESS_TOKEN_EXPIRE_MINUTES", "JWT_EXPIRATION"],
            "mongodb_url": ["MONGODB_URL", "DATABASE_URL"]
        }
    }

    @property
    def access_token_expires(self) -> timedelta:
        return timedelta(minutes=self.access_token_expire_minutes)

    @property
    def refresh_token_expires(self) -> timedelta:
        return timedelta(days=self.refresh_token_expire_days)

@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()