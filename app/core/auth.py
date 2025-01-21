# backend/app/core/auth.py

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status, Cookie
from fastapi.security import OAuth2PasswordBearer
import logging
import redis
from bson import ObjectId

from ..config import get_settings
from ..models.user import User, TokenData, Role
from .security import verify_password
from ..services.database import get_user_by_id

# Initialize logging and settings
logger = logging.getLogger(__name__)
settings = get_settings()

# OAuth2 configuration
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# Redis client for token management
redis_client = redis.Redis(
    host=settings.redis_host,
    port=settings.redis_port,
    db=settings.redis_db,
    password=settings.redis_password,
    decode_responses=True
)

class TokenManager:
    @staticmethod
    def create_token(data: Dict[str, Any], expires_delta: timedelta, secret_key: str) -> str:
        """Create a JWT token with given data and expiration."""
        to_encode = data.copy()
        expire = datetime.utcnow() + expires_delta
        to_encode.update({"exp": expire})
        
        return jwt.encode(
            to_encode,
            secret_key,
            algorithm=settings.token_algorithm
        )

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

    @staticmethod
    def create_tokens(user_data: Dict[str, Any]) -> Tuple[str, str]:
        """Create both access and refresh tokens for a user."""
        access_token = TokenManager.create_token(
            data={
                "sub": str(user_data["id"]),
                "email": user_data["email"],
                "role": user_data["role"],
                "type": "access"
            },
            expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
            secret_key=settings.access_token_secret
        )

        refresh_token = TokenManager.create_token(
            data={
                "sub": str(user_data["id"]),
                "type": "refresh"
            },
            expires_delta=timedelta(days=settings.refresh_token_expire_days),
            secret_key=settings.refresh_token_secret
        )

        return access_token, refresh_token

class TokenBlacklist:
    @staticmethod
    async def is_blacklisted(token: str) -> bool:
        """Check if a token is blacklisted."""
        try:
            return bool(redis_client.exists(f"blacklist:{token}"))
        except redis.RedisError as e:
            logger.error(f"Redis error checking blacklist: {str(e)}")
            return False

    @staticmethod
    async def add_to_blacklist(token: str, expires_in: int) -> None:
        """Add a token to the blacklist."""
        try:
            redis_client.setex(f"blacklist:{token}", expires_in, "1")
        except redis.RedisError as e:
            logger.error(f"Redis error adding to blacklist: {str(e)}")

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    refresh_token: Optional[str] = Cookie(None, alias="refresh_token")
) -> User:
    """Get current user from access token with auto-refresh capability."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # Check token blacklist
        if await TokenBlacklist.is_blacklisted(token):
            raise credentials_exception

        # Verify access token
        payload = TokenManager.verify_token(token, settings.access_token_secret)
        if not payload:
            if refresh_token:
                refresh_payload = TokenManager.verify_token(
                    refresh_token, 
                    settings.refresh_token_secret
                )
                if refresh_payload and refresh_payload.get("type") == "refresh":
                    user = await get_user_by_id(refresh_payload.get("sub"))
                    if user:
                        return user
            raise credentials_exception

        user_id = payload.get("sub")
        if not user_id:
            raise credentials_exception

        user = await get_user_by_id(user_id)
        if not user:
            raise credentials_exception

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Inactive user"
            )

        return user

    except Exception as e:
        logger.error(f"Authentication error: {str(e)}")
        raise credentials_exception

async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Ensure the current user is active."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    return current_user

async def get_current_admin_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Ensure the current user has admin privileges."""
    if current_user.role != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return current_user

# Export public interface
__all__ = [
    'TokenManager',
    'TokenBlacklist',
    'get_current_user',
    'get_current_active_user',
    'get_current_admin_user'
]