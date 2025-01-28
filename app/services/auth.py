"""Authentication service providing core security functionality.

This service manages user authentication, token handling, and authorization checks.
It implements secure practices for password verification, token generation, and 
session management while maintaining detailed logging for security auditing.
"""

from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any
from fastapi import Depends, HTTPException, status, Response, Cookie
from fastapi.security import OAuth2PasswordBearer
import logging
from bson import ObjectId
import redis

from ..config import get_settings
from ..models.user import User, UserInDB, TokenData, Role
from ..core.security import SecurityManager
from ..core.auth import TokenManager
from .database import get_user_by_email, get_user_by_id

logger = logging.getLogger(__name__)
settings = get_settings()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

redis_client = redis.Redis(
    host=settings.redis_host,
    port=settings.redis_port,
    db=settings.redis_db,
    password=settings.redis_password,
    decode_responses=True
)

async def authenticate_user(email: str, password: str) -> Optional[User]:
    """Authenticate a user and return their user object if successful."""
    try:
        logger.info(f"Starting authentication process for user: {email}")
        
        user = await get_user_by_email(email)
        if not user:
            logger.warning(f"Authentication failed - user not found: {email}")
            return None

        if not SecurityManager.verify_password(password, user.hashed_password):
            logger.warning(f"Authentication failed - invalid password: {email}")
            return None

        if not user.is_active:
            logger.warning(f"Authentication failed - inactive user: {email}")
            return None

        logger.info(f"Authentication successful for user: {email}")
        return user

    except Exception as e:
        logger.error(f"Authentication error: {str(e)}", exc_info=True)
        raise
def create_tokens(user_data: Dict[str, Any]) -> Tuple[str, str]:
    """Create access and refresh tokens for a user.
    
    Args:
        user_data: Dictionary containing user information for token creation
        
    Returns:
        Tuple containing (access_token, refresh_token)
    """
    try:
        access_token = TokenManager.create_token(
            data={
                "sub": str(user_data["id"]),
                "email": user_data.get("email"),
                "role": user_data.get("role", "user"),
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

    except Exception as e:
        logger.error(f"Token creation error: {str(e)}")
        raise RuntimeError("Failed to create authentication tokens")

async def create_user_session(user: User) -> Tuple[str, str]:
    """Create a new session for an authenticated user.

    This function generates access and refresh tokens for a user session,
    implementing secure token generation and proper session management.

    Args:
        user: The authenticated user object

    Returns:
        Tuple containing access token and refresh token

    Raises:
        Exception: If token generation fails
    """
    try:
        user_data = {
            "id": str(user.id),
            "email": user.email,
            "role": user.role
        }

        access_token, refresh_token = TokenManager.create_tokens(user_data)
        
        await store_refresh_token(
            str(user.id),
            refresh_token,
            datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days)
        )

        return access_token, refresh_token

    except Exception as e:
        logger.error(f"Session creation error: {str(e)}", exc_info=True)
        raise

async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """Get the current authenticated user.
    
    This function validates the access token and returns the current user.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # Verify the token
        payload = TokenManager.verify_token(token, settings.access_token_secret)
        if payload is None:
            raise credentials_exception
            
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
            
        # Get user from database
        user = await get_user_by_id(ObjectId(user_id))
        if user is None:
            raise credentials_exception
            
        # Convert to User model and return
        return User(**user.model_dump(exclude={'hashed_password'}))
        
    except Exception as e:
        raise credentials_exception

async def authenticate_user(email: str, password: str) -> Optional[UserInDB]:
    """Authenticate a user and return their database record."""
    # Your existing authenticate_user implementation
    pass

async def handle_token_refresh(refresh_token: str) -> Optional[User]:
    """Handle the refresh token process for session renewal.

    This function manages the token refresh process, including validation
    of the refresh token and generation of new access tokens.

    Args:
        refresh_token: The refresh token to validate

    Returns:
        Updated user object if refresh successful, None otherwise
    """
    try:
        refresh_payload = TokenManager.verify_token(
            refresh_token,
            settings.refresh_token_secret
        )

        if refresh_payload and refresh_payload.get("type") == "refresh":
            user = await get_user_by_id(refresh_payload.get("sub"))
            if user:
                return user
        return None

    except Exception as e:
        logger.error(f"Token refresh error: {str(e)}", exc_info=True)
        return None

async def get_current_admin_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Get the current user and verify they have admin privileges."""
    if current_user.role != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )
    return current_user