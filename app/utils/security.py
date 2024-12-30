# backend/app/utils/security.py
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import secrets

from ..config import get_settings
from ..models.user import UserInDB
from ..services.database import get_user_by_id, get_user_by_reset_token

settings = get_settings()

# Password hashing configuration
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 configuration for token handling
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

def get_password_hash(password: str) -> str:
    """Generate a secure hash from a password."""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)

def create_verification_token() -> str:
    """Generate a secure token for email verification."""
    return secrets.token_urlsafe(32)

def verify_token(token: str) -> Optional[dict]:
    """Verify a JWT token and return its payload."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        return payload
    except JWTError:
        return None

async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserInDB:
    """Get the current authenticated user from a JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    payload = verify_token(token)
    if not payload or "user_id" not in payload:
        raise credentials_exception
    
    user = await get_user_by_id(payload["user_id"])
    if not user:
        raise credentials_exception
    
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified"
        )
    
    return user

def create_reset_token() -> tuple[str, datetime]:
    """Create a password reset token with expiration."""
    expiration = datetime.utcnow() + timedelta(hours=24)
    token = secrets.token_urlsafe(32)
    return token, expiration

async def verify_reset_token(token: str) -> Optional[str]:
    """Verify a password reset token and return the user ID if valid."""
    try:
        user = await get_user_by_reset_token(token)
        if not user or user.reset_token_expires < datetime.utcnow():
            return None
        return user.id
    except:
        return None

def require_admin(current_user: UserInDB = Depends(get_current_user)):
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