# backend/app/utils/security.py


from datetime import datetime, timedelta
from typing import Optional, Tuple
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Response, Cookie
from fastapi.security import OAuth2PasswordBearer
import secrets
import redis
import logging

from ..config import get_settings
from ..models.user import UserInDB, User, Role
from ..services.auth import get_current_user


# Setup logging
logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()

# Password hashing configuration
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 configuration
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# Redis client for token blacklisting
redis_client = redis.Redis(
    host=settings.redis_host,
    port=settings.redis_port,
    db=settings.redis_db,
    password=settings.redis_password,
    decode_responses=True
)

def get_password_hash(password: str) -> str:
    """Generate a secure hash from a password."""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)

def create_verification_token() -> str:
    """Generate a secure token for email verification."""
    return secrets.token_urlsafe(32)

def create_tokens(user_data: dict) -> Tuple[str, str]:
    """Create access and refresh tokens."""
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_token(
        data={
            "sub": str(user_data["id"]),
            "email": user_data["email"],
            "role": user_data["role"],
            "type": "access"
        },
        expires_delta=access_token_expires
    )

    refresh_token_expires = timedelta(days=settings.refresh_token_expire_days)
    refresh_token = create_token(
        data={
            "sub": str(user_data["id"]),
            "type": "refresh"
        },
        expires_delta=refresh_token_expires
    )

    return access_token, refresh_token

def create_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.access_token_secret,
        algorithm=settings.token_algorithm
    )
    return encoded_jwt

def verify_token(token: str, verify_type: Optional[str] = None) -> Optional[dict]:
    """Verify a JWT token and return its payload."""
    try:
        secret_key = (settings.refresh_token_secret 
                     if verify_type == "refresh" 
                     else settings.access_token_secret)
        
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=[settings.token_algorithm]
        )
        
        if verify_type and payload.get("type") != verify_type:
            return None
            
        return payload
    except JWTError as e:
        logger.error(f"Token verification failed: {str(e)}")
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
        # Check if token is blacklisted
        if is_token_blacklisted(token):
            raise credentials_exception

        # Verify access token
        payload = verify_token(token)
        if not payload:
            if refresh_token:
                refresh_payload = verify_token(refresh_token, verify_type="refresh")
                if refresh_payload:
                    from ..services.database import get_user_by_id  # Import here to avoid circular import
                    user = await get_user_by_id(refresh_payload.get("sub"))
                    if user:
                        return user
            raise credentials_exception

        user_id = payload.get("sub")
        if not user_id:
            raise credentials_exception

        from ..services.database import get_user_by_id  # Import here to avoid circular import
        user = await get_user_by_id(user_id)
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

#  existing functions remain unchanged
def create_reset_token() -> tuple[str, datetime]:
    """Create a password reset token with expiration."""
    expiration = datetime.utcnow() + timedelta(hours=24)
    token = secrets.token_urlsafe(32)
    return token, expiration

async def verify_reset_token(token: str) -> Optional[str]:
    """Verify a password reset token and return the user ID if valid."""
    try:
        from ..services.database import get_user_by_reset_token  # Import here to avoid circular import
        user = await get_user_by_reset_token(token)
        if not user or user.reset_token_expires < datetime.utcnow():
            return None
        return user.id
    except Exception as e:
        logger.error(f"Reset token verification error: {str(e)}")
        return None

def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Dependency for routes that require admin access."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user

def validate_file_type(filename: str) -> bool:
    """Validate if the uploaded file type is allowed."""
    allowed_extensions = {'.pdf', '.doc', '.docx'}
    return any(filename.lower().endswith(ext) for ext in allowed_extensions)

def generate_secure_filename(filename: str) -> str:
    """Generate a secure filename for uploaded files."""
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    random_suffix = secrets.token_hex(8)
    extension = filename.rsplit('.', 1)[1].lower()
    return f"{timestamp}_{random_suffix}.{extension}"