# backend/app/services/auth.py

from datetime import datetime, timedelta
from typing import Optional, Tuple
from fastapi import Depends, HTTPException, status, Response, Cookie
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
import logging
from bson import ObjectId
import redis

from ..config import get_settings
from ..models.user import User, UserInDB, TokenData, Role
from ..services.database import get_user_by_email, get_user_by_id
from ..core.security import verify_password, get_password_hash

# Setup logging
logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# Redis client for token blacklisting
redis_client = redis.Redis(
    host=settings.redis_host,
    port=settings.redis_port,
    db=settings.redis_db,
    password=settings.redis_password,
    decode_responses=True
)

async def authenticate_user(username: str, password: str) -> Optional[User]:
    """Authenticate a user and return user object if successful."""
    logger.info(f"Starting authentication process for user: {username}")
    
    try:
        # Step 1: Get user by email
        user = await get_user_by_email(username)
        if not user:
            logger.warning(f"User not found: {username}")
            return None

        logger.info(f"User found: {username}")

        # Step 2: Verify password
        if not verify_password(password, user.hashed_password):
            logger.warning(f"Invalid password for user: {username}")
            return None

        logger.info(f"Password verified for user: {username}")

        # Step 3: Check if user is active
        if not user.is_active:
            logger.warning(f"Inactive user attempted login: {username}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Inactive user"
            )

        logger.info(f"User active status verified: {username}")
        return user

    except HTTPException as he:
        logger.error(f"HTTP Exception during authentication: {str(he)}")
        raise he
    except Exception as e:
        logger.error(f"Unexpected error during authentication: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Authentication error: {str(e)}"
        )

def create_tokens(user_data: dict) -> Tuple[str, str]:
    """Create access and refresh tokens."""
    try:
        # Access token - short lived (30 minutes)
        access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
        access_token = create_token(
            data={
                "sub": str(user_data["id"]),
                "email": user_data["email"],
                "role": user_data["role"],
                "type": "access"
            },
            expires_delta=access_token_expires,
            secret_key=settings.access_token_secret
        )

        # Refresh token - long lived (7 days)
        refresh_token_expires = timedelta(days=settings.refresh_token_expire_days)
        refresh_token = create_token(
            data={
                "sub": str(user_data["id"]),
                "type": "refresh"
            },
            expires_delta=refresh_token_expires,
            secret_key=settings.refresh_token_secret
        )

        return access_token, refresh_token
    except Exception as e:
        logger.error(f"Token creation error: {str(e)}")
        raise

def create_token(data: dict, expires_delta: timedelta, secret_key: str) -> str:
    """Create a JWT token."""
    try:
        to_encode = data.copy()
        expire = datetime.utcnow() + expires_delta
        to_encode.update({"exp": int(expire.timestamp())})
        
        encoded_jwt = jwt.encode(
            to_encode,
            secret_key,
            algorithm=settings.token_algorithm
        )
        return encoded_jwt
    except Exception as e:
        logger.error(f"Token encoding error: {str(e)}")
        raise

def verify_token(token: str, secret_key: str) -> Optional[dict]:
    """Verify a token and return its payload."""
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

def is_token_blacklisted(token: str) -> bool:
    """Check if a token is blacklisted."""
    try:
        return bool(redis_client.exists(f"blacklist:{token}"))
    except redis.RedisError as e:
        logger.error(f"Redis error checking blacklist: {str(e)}")
        return False

def blacklist_token(token: str, expires_in: int) -> None:
    """Add a token to the blacklist."""
    try:
        redis_client.setex(f"blacklist:{token}", expires_in, "1")
    except redis.RedisError as e:
        logger.error(f"Redis error adding to blacklist: {str(e)}")

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    refresh_token: Optional[str] = Cookie(None, alias="refresh_token")
) -> User:
    """Get current user from token with auto-refresh capability."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        if is_token_blacklisted(token):
            raise credentials_exception

        payload = verify_token(token, settings.access_token_secret)
        if not payload:
            if refresh_token:
                refresh_payload = verify_token(refresh_token, settings.refresh_token_secret)
                if refresh_payload and refresh_payload.get("type") == "refresh":
                    user = await get_user_by_id(ObjectId(refresh_payload.get("sub")))
                    if user:
                        return user
            raise credentials_exception

        user_id = payload.get("sub")
        if not user_id:
            raise credentials_exception

        user = await get_user_by_id(ObjectId(user_id))
        if not user:
            raise credentials_exception

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Inactive user"
            )

        return user
    except JWTError as e:
        logger.error(f"JWT error: {str(e)}")
        raise credentials_exception
    except Exception as e:
        logger.error(f"Authentication error: {str(e)}")
        raise credentials_exception

def set_refresh_token_cookie(response: Response, refresh_token: str) -> None:
    """Set refresh token as HTTP-only cookie."""
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        domain=settings.cookie_domain,
        samesite=settings.cookie_samesite,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60
    )

def clear_refresh_token_cookie(response: Response) -> None:
    """Clear refresh token cookie."""
    response.delete_cookie(
        key="refresh_token",
        httponly=True,
        secure=settings.cookie_secure,
        domain=settings.cookie_domain,
        samesite=settings.cookie_samesite
    )

async def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """Verify the current user is an admin."""
    if current_user.role != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return current_user