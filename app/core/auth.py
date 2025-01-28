"""Core authentication functionality for token management."""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from jose import JWTError, jwt
import logging
import redis

from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class TokenManager:
    """Handles all token-related operations."""
    
    @staticmethod
    def create_token(data: Dict[str, Any], expires_delta: timedelta, secret_key: str) -> str:
        """Create a JWT token with given data and expiration."""
        try:
            to_encode = data.copy()
            expire = datetime.utcnow() + expires_delta
            to_encode.update({"exp": expire})
            
            encoded_jwt = jwt.encode(
                to_encode,
                secret_key,
                algorithm=settings.token_algorithm
            )
            return encoded_jwt
            
        except Exception as e:
            logger.error(f"Token creation failed: {str(e)}")
            raise ValueError(f"Failed to create token: {str(e)}")

    @staticmethod
    def verify_token(token: str, secret_key: str) -> Optional[Dict[str, Any]]:
        """Verify and decode a JWT token."""
        try:
            payload = jwt.decode(
                token,
                secret_key,
                algorithms=[settings.token_algorithm]
            )
            return payload
        except JWTError as e:
            logger.error(f"Token verification failed: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Token verification error: {str(e)}")
            return None

    @staticmethod
    def create_tokens(user_data: Dict[str, Any]) -> Tuple[str, str]:
        """Create both access and refresh tokens for a user."""
        try:
            # Create access token
            access_token = TokenManager.create_token(
                data={
                    "sub": str(user_data["sub"]),
                    "email": user_data.get("email"),
                    "role": user_data.get("role", "user"),
                    "type": "access"
                },
                expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
                secret_key=settings.access_token_secret
            )

            # Create refresh token
            refresh_token = TokenManager.create_token(
                data={
                    "sub": str(user_data["sub"]),
                    "type": "refresh"
                },
                expires_delta=timedelta(days=settings.refresh_token_expire_days),
                secret_key=settings.refresh_token_secret
            )

            return access_token, refresh_token

        except Exception as e:
            logger.error(f"Token creation error: {str(e)}")
            raise ValueError(f"Failed to create tokens: {str(e)}")

class TokenBlacklist:
    """Manages blacklisted tokens using Redis."""
    
    _redis_client = redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        password=settings.redis_password,
        decode_responses=True
    )

    @classmethod
    async def is_blacklisted(cls, token: str) -> bool:
        """Check if a token is blacklisted."""
        try:
            return bool(cls._redis_client.exists(f"blacklist:{token}"))
        except redis.RedisError as e:
            logger.error(f"Redis error checking blacklist: {str(e)}")
            return False

    @classmethod
    async def add_to_blacklist(cls, token: str, expires_in: int) -> None:
        """Add a token to the blacklist."""
        try:
            cls._redis_client.setex(f"blacklist:{token}", expires_in, "1")
        except redis.RedisError as e:
            logger.error(f"Redis error adding to blacklist: {str(e)}")